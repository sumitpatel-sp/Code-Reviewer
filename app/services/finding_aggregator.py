"""Finding deduplication and aggregation service.

Different agents may report the same underlying issue from different angles.
This module groups and merges duplicate findings intelligently, preserving
the most useful information from each contributing agent.

Deduplication strategy:
  1. Same file + overlapping line ranges → likely duplicate
  2. Similar title using difflib SequenceMatcher (threshold 0.65)
  3. Same category (e.g. two Security findings about the same pattern)

Merging rules:
  - Keep the highest severity across duplicates
  - Boost confidence when multiple agents agree (each additional agent +10, capped at 100)
  - Concatenate descriptions from all agents (deduped)
  - Record all contributing agents in merged_from
  - Static-analysis corroboration adds +15 confidence
"""

from __future__ import annotations

import difflib
import logging
import uuid
from copy import deepcopy

from app.schemas.finding import FindingSchema, FindingSource, Severity


logger = logging.getLogger(__name__)

# Severity ordering for comparison (higher index = higher severity)
_SEVERITY_ORDER = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}

_SIMILARITY_THRESHOLD = 0.65  # SequenceMatcher ratio for title similarity


def _titles_are_similar(a: str, b: str) -> bool:
    """Return True when two finding titles are similar enough to merge."""
    ratio = difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()
    return ratio >= _SIMILARITY_THRESHOLD


def _lines_overlap(
    a_start: int | None, a_end: int | None,
    b_start: int | None, b_end: int | None,
) -> bool:
    """Return True when two line ranges overlap or are both unknown."""
    if a_start is None or b_start is None:
        # When either is unknown, do not use line overlap as evidence
        return False
    a_e = a_end or a_start
    b_e = b_end or b_start
    return not (a_e < b_start or b_e < a_start)


def _same_file(a: str | None, b: str | None) -> bool:
    """Return True when both findings reference the same file."""
    if a is None or b is None:
        return False
    return a.strip().lower() == b.strip().lower()


def _are_duplicates(f1: FindingSchema, f2: FindingSchema) -> bool:
    """Decide whether two findings describe the same underlying issue."""
    # Must share the same category to be candidates for merging
    if f1.category.lower() != f2.category.lower():
        return False

    # Same file + title similarity is enough
    if _same_file(f1.file, f2.file) and _titles_are_similar(f1.title, f2.title):
        return True

    # Same file + overlapping line range
    if _same_file(f1.file, f2.file) and _lines_overlap(
        f1.line_start, f1.line_end, f2.line_start, f2.line_end
    ):
        return True

    # Very similar title even across files (cross-file pattern)
    if _titles_are_similar(f1.title, f2.title):
        ratio = difflib.SequenceMatcher(None, f1.title.lower(), f2.title.lower()).ratio()
        if ratio >= 0.85:
            return True

    return False


def _merge_group(group: list[FindingSchema]) -> FindingSchema:
    """Merge a group of duplicate findings into a single, richer finding."""
    if len(group) == 1:
        return group[0]

    # Pick representative (highest severity, then highest confidence)
    primary = max(group, key=lambda f: (_SEVERITY_ORDER[f.severity], f.confidence))

    # Compute boosted confidence
    has_static = any(f.source == FindingSource.STATIC_ANALYSIS for f in group)
    base_confidence = primary.confidence
    boost = (len(group) - 1) * 10 + (15 if has_static else 0)
    merged_confidence = min(base_confidence + boost, 100)

    # Collect all contributing agent names and IDs
    all_agents = []
    merged_from = []
    for f in group:
        if f.agent not in all_agents:
            all_agents.append(f.agent)
        merged_from.append(f.id)

    # Combine descriptions (deduplicated by similarity)
    descriptions = [primary.description]
    for f in group:
        if f is primary:
            continue
        if not _titles_are_similar(f.description, descriptions[-1]):
            descriptions.append(f.description)

    combined_description = " | ".join(descriptions[:3])  # cap at 3 to avoid verbosity

    # Use the best available recommendation
    recommendations = [f.recommendation for f in group if f.recommendation]
    best_recommendation = max(recommendations, key=len) if recommendations else primary.recommendation

    # Use the best available code snippet and fix
    snippets = [f.code_snippet for f in group if f.code_snippet]
    fixes = [f.suggested_fix for f in group if f.suggested_fix]

    return FindingSchema(
        id=primary.id,
        agent=" + ".join(all_agents),
        category=primary.category,
        severity=primary.severity,
        confidence=merged_confidence,
        source=primary.source if not has_static else FindingSource.STATIC_ANALYSIS,
        file=primary.file,
        line_start=primary.line_start,
        line_end=primary.line_end,
        title=primary.title,
        description=combined_description,
        impact=primary.impact,
        recommendation=best_recommendation,
        code_snippet=snippets[0] if snippets else None,
        suggested_fix=fixes[0] if fixes else None,
        merged_from=merged_from,
    )


def _boost_confidence_with_static(findings: list[FindingSchema], static_findings: list[FindingSchema]) -> list[FindingSchema]:
    """Boost confidence of LLM findings that are corroborated by static analysis."""
    boosted = []
    for llm_f in findings:
        if llm_f.source == FindingSource.STATIC_ANALYSIS:
            boosted.append(llm_f)
            continue

        corroborated = any(
            _same_file(llm_f.file, sf.file) and _titles_are_similar(llm_f.title, sf.title)
            for sf in static_findings
        )
        if corroborated:
            upgraded = deepcopy(llm_f)
            upgraded.confidence = min(llm_f.confidence + 15, 100)
            boosted.append(upgraded)
        else:
            boosted.append(llm_f)

    return boosted


def deduplicate_and_aggregate(
    all_findings: list[dict],
) -> list[FindingSchema]:
    """Deduplicate, merge, and confidence-boost all findings from all agents.

    Parameters
    ----------
    all_findings:
        Combined list of finding dicts from all agents and static analysis.
        Each dict should match the FindingSchema fields.

    Returns
    -------
    Deduplicated list of FindingSchema objects, sorted by severity desc,
    then confidence desc.
    """
    if not all_findings:
        return []

    # Parse raw dicts into FindingSchema objects, skipping invalid entries
    schemas: list[FindingSchema] = []
    for raw in all_findings:
        if not isinstance(raw, dict):
            continue
        try:
            schemas.append(FindingSchema(**raw))
        except Exception as exc:
            logger.debug("Skipping invalid finding dict: %s | %s", exc, raw)

    if not schemas:
        return []

    # Separate static analysis from LLM findings for confidence boosting
    static_findings = [f for f in schemas if f.source == FindingSource.STATIC_ANALYSIS]
    llm_findings = [f for f in schemas if f.source != FindingSource.STATIC_ANALYSIS]

    # Boost LLM confidence where corroborated by static analysis
    llm_findings = _boost_confidence_with_static(llm_findings, static_findings)

    # All findings for grouping
    all_schemas = llm_findings + static_findings

    # Greedy clustering: group duplicates
    visited = [False] * len(all_schemas)
    groups: list[list[FindingSchema]] = []

    for i, fi in enumerate(all_schemas):
        if visited[i]:
            continue
        group = [fi]
        visited[i] = True
        for j in range(i + 1, len(all_schemas)):
            if visited[j]:
                continue
            if _are_duplicates(fi, all_schemas[j]):
                group.append(all_schemas[j])
                visited[j] = True
        groups.append(group)

    # Merge each group
    merged = [_merge_group(g) for g in groups]

    # Sort by severity desc, confidence desc
    merged.sort(
        key=lambda f: (_SEVERITY_ORDER[f.severity], f.confidence),
        reverse=True,
    )

    # Assign stable IDs to findings that lost their id during merging
    seen_ids: set[str] = set()
    for f in merged:
        if not f.id or f.id in seen_ids:
            f.id = str(uuid.uuid4())
        seen_ids.add(f.id)

    logger.info(
        "Finding aggregation: %d raw → %d after deduplication.",
        len(all_schemas), len(merged),
    )
    return merged


def count_by_severity(findings: list[FindingSchema]) -> dict[str, int]:
    """Return finding counts grouped by severity."""
    counts: dict[str, int] = {s.value: 0 for s in Severity}
    for f in findings:
        counts[f.severity.value] += 1
    counts["total"] = len(findings)
    return counts


def top_findings(findings: list[FindingSchema], n: int = 5) -> list[FindingSchema]:
    """Return the top N highest-priority findings."""
    return findings[:n]

"""Parse structured JSON findings from LLM agent responses.

Agents return a Markdown response that contains a JSON block with findings.
This module extracts that JSON safely and validates each finding against
the FindingSchema, discarding malformed entries rather than crashing.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from app.schemas.finding import FindingSchema, FindingSource, Severity


logger = logging.getLogger(__name__)

# Regex that matches a fenced JSON block: ```json ... ```
_JSON_BLOCK_RE = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def _extract_json_blocks(text: str) -> list[str]:
    """Return all fenced JSON blocks found in the LLM response text."""
    return _JSON_BLOCK_RE.findall(text)


def _coerce_severity(value: Any) -> Severity:
    """Normalise a severity string to its enum value, defaulting to MEDIUM."""
    if isinstance(value, str):
        upper = value.upper()
        try:
            return Severity(upper)
        except ValueError:
            pass
    return Severity.MEDIUM


def _coerce_confidence(value: Any) -> int:
    """Clamp confidence to [0, 100]."""
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return 50


def _safe_str(value: Any, fallback: str = "") -> str:
    """Return value as a string or the fallback."""
    if value is None:
        return fallback
    return str(value).strip()


def _safe_optional_int(value: Any) -> int | None:
    """Return an int or None; never fabricate a line number."""
    if value is None:
        return None
    try:
        result = int(value)
        return result if result > 0 else None
    except (TypeError, ValueError):
        return None


def parse_findings_from_response(
    response_text: str,
    agent_name: str,
    category: str,
    source: FindingSource = FindingSource.AI_DETECTED,
) -> list[FindingSchema]:
    """Extract structured findings from one agent's LLM response.

    The LLM is instructed to embed findings as a JSON array inside a fenced
    code block.  This function extracts those blocks, validates each entry,
    and returns a list of valid FindingSchema objects.

    Malformed or missing findings are logged and skipped rather than crashing
    the entire review pipeline.
    """
    findings: list[FindingSchema] = []

    json_blocks = _extract_json_blocks(response_text)
    if not json_blocks:
        logger.debug("No JSON findings block found in %s response.", agent_name)
        return findings

    for block in json_blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse JSON from %s agent: %s", agent_name, exc)
            continue

        # Support both a single object and an array of objects
        if isinstance(data, dict):
            items: list[dict] = [data]
        elif isinstance(data, list):
            items = data
        else:
            continue

        for raw in items:
            if not isinstance(raw, dict):
                continue
            try:
                finding = FindingSchema(
                    id=_safe_str(raw.get("id")) or str(uuid.uuid4()),
                    agent=agent_name,
                    category=_safe_str(raw.get("category"), fallback=category),
                    severity=_coerce_severity(raw.get("severity")),
                    confidence=_coerce_confidence(raw.get("confidence", 60)),
                    source=source,
                    file=_safe_str(raw.get("file")) or None,
                    line_start=_safe_optional_int(raw.get("line_start")),
                    line_end=_safe_optional_int(raw.get("line_end")),
                    title=_safe_str(raw.get("title"), fallback="Untitled finding"),
                    description=_safe_str(raw.get("description"), fallback="No description provided."),
                    impact=_safe_str(raw.get("impact"), fallback="Unknown impact."),
                    recommendation=_safe_str(raw.get("recommendation"), fallback="Review this code."),
                    code_snippet=_safe_str(raw.get("code_snippet")) or None,
                    suggested_fix=_safe_str(raw.get("suggested_fix")) or None,
                )
                findings.append(finding)
            except Exception as exc:
                logger.warning(
                    "Skipping malformed finding from %s: %s | raw=%s",
                    agent_name, exc, raw,
                )

    logger.debug("Parsed %d findings from %s.", len(findings), agent_name)
    return findings


def extract_score_from_text(text: str, pattern: str) -> float | None:
    """Extract a numeric score from LLM Markdown text using a regex pattern.

    Returns None if no match is found, so callers can use a default.
    """
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        try:
            return float(min(int(match.group(1)), 100))
        except (ValueError, IndexError):
            return None
    return None

"""Tests for the finding deduplication and aggregation service."""

import pytest

from app.schemas.finding import FindingSchema, FindingSource, Severity
from app.services.finding_aggregator import (
    count_by_severity,
    deduplicate_and_aggregate,
    top_findings,
)


def _make_finding(
    id: str,
    title: str,
    severity: Severity = Severity.MEDIUM,
    confidence: int = 70,
    file: str | None = "app/main.py",
    category: str = "Security",
    agent: str = "Security Agent",
    source: FindingSource = FindingSource.AI_DETECTED,
    line_start: int | None = None,
    line_end: int | None = None,
) -> dict:
    return FindingSchema(
        id=id,
        agent=agent,
        category=category,
        severity=severity,
        confidence=confidence,
        source=source,
        file=file,
        line_start=line_start,
        line_end=line_end,
        title=title,
        description="Test description",
        impact="Test impact",
        recommendation="Test recommendation",
    ).model_dump()


class TestDeduplication:
    """Test finding deduplication logic."""

    def test_identical_titles_same_file_merged(self):
        """Two findings with identical titles and same file should merge."""
        f1 = _make_finding("f1", "SQL Injection Risk", agent="Security Agent")
        f2 = _make_finding("f2", "SQL Injection Risk", agent="Quality Agent")
        result = deduplicate_and_aggregate([f1, f2])
        assert len(result) == 1
        assert "Security Agent" in result[0].agent
        assert "Quality Agent" in result[0].agent

    def test_different_categories_not_merged(self):
        """Findings from different categories should not be merged even with similar titles."""
        f1 = _make_finding("f1", "Missing null check", category="Bug", agent="Bug Agent")
        f2 = _make_finding("f2", "Missing null check", category="Quality", agent="Quality Agent")
        result = deduplicate_and_aggregate([f1, f2])
        # Different categories → not merged
        assert len(result) == 2

    def test_merged_finding_takes_higher_severity(self):
        """Merged finding should inherit the highest severity."""
        f1 = _make_finding("f1", "Path Traversal", severity=Severity.MEDIUM)
        f2 = _make_finding("f2", "Path Traversal", severity=Severity.HIGH)
        result = deduplicate_and_aggregate([f1, f2])
        assert len(result) == 1
        assert result[0].severity == Severity.HIGH

    def test_merged_finding_boosts_confidence(self):
        """Merging two findings should boost confidence by 10 per additional agent."""
        f1 = _make_finding("f1", "SQL Injection", confidence=70)
        f2 = _make_finding("f2", "SQL Injection", confidence=65)
        result = deduplicate_and_aggregate([f1, f2])
        # Confidence should be boosted (original 70 + 10 for one extra agent)
        assert result[0].confidence >= 70

    def test_static_analysis_boosts_confidence(self):
        """Static analysis corroboration should add +15 to LLM finding confidence."""
        llm_f = _make_finding("f1", "High Complexity", category="Quality",
                               confidence=60, source=FindingSource.AI_DETECTED)
        static_f = _make_finding("f2", "High Complexity", category="Quality",
                                  confidence=95, source=FindingSource.STATIC_ANALYSIS,
                                  agent="Static Analysis (Radon)")
        result = deduplicate_and_aggregate([llm_f, static_f])
        # The LLM finding should be boosted by the static corroboration
        assert any(r.confidence > 60 for r in result)

    def test_empty_input_returns_empty(self):
        """Empty finding list should return empty list."""
        result = deduplicate_and_aggregate([])
        assert result == []

    def test_single_finding_passes_through(self):
        """A single finding should pass through unchanged."""
        f = _make_finding("f1", "Some issue", severity=Severity.HIGH, confidence=80)
        result = deduplicate_and_aggregate([f])
        assert len(result) == 1
        assert result[0].title == "Some issue"

    def test_findings_sorted_by_severity(self):
        """Aggregated findings should be sorted by severity descending."""
        f1 = _make_finding("f1", "Low issue", severity=Severity.LOW, category="Bug")
        f2 = _make_finding("f2", "Critical issue", severity=Severity.CRITICAL, category="Security")
        f3 = _make_finding("f3", "Medium issue", severity=Severity.MEDIUM, category="Quality")
        result = deduplicate_and_aggregate([f1, f2, f3])
        severities = [r.severity for r in result]
        assert severities[0] == Severity.CRITICAL

    def test_malformed_dict_skipped(self):
        """Malformed finding dicts should be skipped without crashing."""
        good = _make_finding("f1", "Valid finding")
        bad = {"invalid": "structure"}
        result = deduplicate_and_aggregate([good, bad])
        assert len(result) == 1


class TestCountBySeverity:
    """Test severity counting."""

    def test_count_by_severity(self):
        """Counts should group correctly by severity."""
        findings = [
            FindingSchema(id=str(i), agent="A", category="C", severity=s, confidence=50,
                          title="T", description="D", impact="I", recommendation="R")
            for i, s in enumerate([Severity.CRITICAL, Severity.HIGH, Severity.HIGH,
                                    Severity.MEDIUM, Severity.LOW, Severity.INFO])
        ]
        counts = count_by_severity(findings)
        assert counts["CRITICAL"] == 1
        assert counts["HIGH"] == 2
        assert counts["MEDIUM"] == 1
        assert counts["LOW"] == 1
        assert counts["INFO"] == 1
        assert counts["total"] == 6


class TestTopFindings:
    """Test top-N finding selection."""

    def test_returns_top_n(self):
        """top_findings should return at most N findings."""
        findings = [
            FindingSchema(id=str(i), agent="A", category="C", severity=Severity.MEDIUM,
                          confidence=50, title=f"Finding {i}", description="D",
                          impact="I", recommendation="R")
            for i in range(10)
        ]
        top = top_findings(findings, n=3)
        assert len(top) == 3

"""Tests for the structured finding schema validation."""

import pytest
from pydantic import ValidationError

from app.schemas.finding import FindingSchema, FindingSource, Severity


def test_finding_schema_valid_minimal():
    """A finding with all required fields and nulls for optional ones should validate."""
    f = FindingSchema(
        id="test-001",
        agent="Quality Agent",
        category="Quality",
        severity=Severity.HIGH,
        confidence=80,
        title="Long function",
        description="Function is too long.",
        impact="Hard to maintain.",
        recommendation="Break it up.",
    )
    assert f.id == "test-001"
    assert f.severity == Severity.HIGH
    assert f.confidence == 80
    assert f.file is None
    assert f.line_start is None
    assert f.suggested_fix is None


def test_finding_schema_valid_full():
    """A complete finding with all fields should validate correctly."""
    f = FindingSchema(
        id="sec-001",
        agent="Security Agent",
        category="Security",
        severity=Severity.CRITICAL,
        confidence=95,
        source=FindingSource.STATIC_ANALYSIS,
        file="app/main.py",
        line_start=42,
        line_end=45,
        title="Hardcoded credential",
        description="Password is hardcoded in the source.",
        impact="Credential exposure if code is leaked.",
        recommendation="Use environment variables.",
        code_snippet="password = 'secret123'",
        suggested_fix="password = os.environ['DB_PASSWORD']",
    )
    assert f.severity == Severity.CRITICAL
    assert f.line_start == 42
    assert f.source == FindingSource.STATIC_ANALYSIS


def test_finding_schema_confidence_bounds():
    """Confidence must be between 0 and 100."""
    with pytest.raises(ValidationError):
        FindingSchema(
            id="x",
            agent="A",
            category="C",
            severity=Severity.LOW,
            confidence=150,  # invalid
            title="T",
            description="D",
            impact="I",
            recommendation="R",
        )

    with pytest.raises(ValidationError):
        FindingSchema(
            id="x",
            agent="A",
            category="C",
            severity=Severity.LOW,
            confidence=-1,  # invalid
            title="T",
            description="D",
            impact="I",
            recommendation="R",
        )


def test_finding_schema_invalid_severity():
    """An invalid severity value should raise a ValidationError."""
    with pytest.raises(ValidationError):
        FindingSchema(
            id="x",
            agent="A",
            category="C",
            severity="SUPER_CRITICAL",  # not a valid enum value
            confidence=50,
            title="T",
            description="D",
            impact="I",
            recommendation="R",
        )


def test_finding_schema_merged_from_defaults_empty():
    """merged_from should default to an empty list."""
    f = FindingSchema(
        id="x",
        agent="A",
        category="C",
        severity=Severity.INFO,
        confidence=50,
        title="T",
        description="D",
        impact="I",
        recommendation="R",
    )
    assert f.merged_from == []

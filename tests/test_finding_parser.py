"""Tests for the LLM response finding parser."""

import json

from app.agents.finding_parser import parse_findings_from_response, extract_score_from_text
from app.schemas.finding import FindingSource, Severity


SAMPLE_RESPONSE = """
## Quality Score: 72

Some narrative text here.

```json
[
  {
    "id": "quality-001",
    "agent": "Quality Agent",
    "category": "Quality",
    "severity": "HIGH",
    "confidence": 80,
    "file": "app/main.py",
    "line_start": null,
    "line_end": null,
    "title": "Long function detected",
    "description": "The function handle_request is 120 lines long.",
    "impact": "Hard to test and maintain.",
    "recommendation": "Split into smaller functions.",
    "code_snippet": null,
    "suggested_fix": null
  },
  {
    "id": "quality-002",
    "agent": "Quality Agent",
    "category": "Quality",
    "severity": "LOW",
    "confidence": 60,
    "file": null,
    "line_start": null,
    "line_end": null,
    "title": "Missing docstrings",
    "description": "Several functions lack docstrings.",
    "impact": "Reduced readability.",
    "recommendation": "Add docstrings to all public functions.",
    "code_snippet": null,
    "suggested_fix": "def my_func():\\n    \\\"\\\"\\\"Add docstring here.\\\"\\\"\\\"\\n    pass"
  }
]
```
"""


def test_parse_valid_findings():
    """Parser should extract two valid findings from the sample response."""
    findings = parse_findings_from_response(
        SAMPLE_RESPONSE, "Quality Agent", "Quality", FindingSource.AI_DETECTED
    )
    assert len(findings) == 2
    assert findings[0].id == "quality-001"
    assert findings[0].severity == Severity.HIGH
    assert findings[0].confidence == 80
    assert findings[0].line_start is None
    assert findings[1].severity == Severity.LOW


def test_parse_empty_response():
    """Parser should return empty list when no JSON block is present."""
    findings = parse_findings_from_response(
        "No findings here.", "Quality Agent", "Quality"
    )
    assert findings == []


def test_parse_malformed_json():
    """Parser should return empty list when JSON block is malformed."""
    response = "```json\n{broken json\n```"
    findings = parse_findings_from_response(response, "Quality Agent", "Quality")
    assert findings == []


def test_parse_single_object_not_array():
    """Parser should handle a single JSON object (not array) in the block."""
    response = """```json
{
  "id": "single-001",
  "agent": "Bug Agent",
  "category": "Bug",
  "severity": "MEDIUM",
  "confidence": 70,
  "file": "app/utils.py",
  "line_start": 15,
  "line_end": 18,
  "title": "Null check missing",
  "description": "Variable may be None here.",
  "impact": "NullPointerException.",
  "recommendation": "Add a None check.",
  "code_snippet": null,
  "suggested_fix": null
}
```"""
    findings = parse_findings_from_response(response, "Bug Agent", "Bug")
    assert len(findings) == 1
    assert findings[0].title == "Null check missing"
    assert findings[0].line_start == 15


def test_parse_missing_optional_fields():
    """Parser should handle findings with missing optional fields gracefully."""
    response = """```json
[
  {
    "id": "x-001",
    "agent": "Sec Agent",
    "category": "Security",
    "severity": "CRITICAL",
    "confidence": 90,
    "title": "SQL Injection",
    "description": "Unsanitized input.",
    "impact": "Data breach.",
    "recommendation": "Use parameterized queries."
  }
]
```"""
    findings = parse_findings_from_response(response, "Security Agent", "Security")
    assert len(findings) == 1
    assert findings[0].file is None
    assert findings[0].code_snippet is None


def test_extract_score_from_text():
    """Score extractor should find a labelled score in Markdown text."""
    text = "## Quality Score: 75\n\nSome text here."
    score = extract_score_from_text(text, r"Quality Score:\s*(\d{1,3})")
    assert score == 75.0


def test_extract_score_not_found():
    """Score extractor should return None when the pattern is absent."""
    score = extract_score_from_text("No score here.", r"Quality Score:\s*(\d{1,3})")
    assert score is None


def test_parse_agent_name_override():
    """The agent field in parsed findings should use the passed agent_name."""
    response = """```json
[{"id":"x","agent":"wrong","category":"Bug","severity":"LOW","confidence":50,
  "title":"T","description":"D","impact":"I","recommendation":"R"}]
```"""
    findings = parse_findings_from_response(response, "Bug Agent", "Bug")
    # agent_name parameter overrides the JSON value
    assert findings[0].agent == "Bug Agent"

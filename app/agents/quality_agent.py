"""LangGraph node that reviews code readability and maintainability."""

import time

from app.agents.finding_parser import parse_findings_from_response
from app.agents.gemini_client import generate_agent_report
from app.langgraph.state import ReviewState
from app.schemas.finding import FindingSource


QUALITY_INSTRUCTIONS = """
You are the Code Quality Agent in a professional AI-powered code-review platform.
Review the supplied source code for naming conventions, readability, duplicate code,
function size, comments, and maintainability.

YOUR RESPONSE MUST HAVE TWO PARTS:

PART 1 — NARRATIVE (Markdown with these exact headings):
1. Quality Score (a whole number from 0 to 100)
2. Strengths
3. Issues (include file paths when possible)
4. Suggestions (ordered by impact)

PART 2 — STRUCTURED FINDINGS (a fenced JSON block):
Output a JSON array of findings using EXACTLY this schema. Every field is required.
Use null for line_start/line_end if you cannot reliably determine them from the source.
Do NOT invent line numbers.

```json
[
  {
    "id": "quality-001",
    "agent": "Quality Agent",
    "category": "Quality",
    "severity": "HIGH",
    "confidence": 80,
    "file": "path/to/file.py",
    "line_start": null,
    "line_end": null,
    "title": "Short, clear title",
    "description": "Detailed explanation of the issue.",
    "impact": "What harm this causes.",
    "recommendation": "How to fix it.",
    "code_snippet": "problematic code here or null",
    "suggested_fix": "improved version or null"
  }
]
```

SEVERITY must be one of: CRITICAL, HIGH, MEDIUM, LOW, INFO
CONFIDENCE (0-100): how certain you are that this is a real issue based solely on the provided source.
Do not invent files, issues, or code that are not present in the source.
"""


def run_quality_agent(state: ReviewState) -> dict:
    """Analyze source files and add the quality report and findings to graph state."""
    start = time.time()
    quality_report = generate_agent_report(QUALITY_INSTRUCTIONS, state["source_files"])
    elapsed = time.time() - start

    findings = parse_findings_from_response(
        quality_report,
        agent_name="Quality Agent",
        category="Quality",
        source=FindingSource.AI_DETECTED,
    )

    existing_findings = list(state.get("findings", []))
    existing_findings.extend(f.model_dump() for f in findings)

    timing = dict(state.get("agent_timing", {}))
    timing["Quality Agent"] = round(elapsed, 2)

    return {
        "quality_report": quality_report,
        "findings": existing_findings,
        "agent_timing": timing,
    }
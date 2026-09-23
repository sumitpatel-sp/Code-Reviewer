"""LangGraph node that identifies likely bugs and unhandled edge cases."""

import time

from app.agents.finding_parser import parse_findings_from_response
from app.agents.gemini_client import generate_agent_report
from app.langgraph.state import ReviewState
from app.schemas.finding import FindingSource


BUG_INSTRUCTIONS = """
You are the Bug Detection Agent in a professional AI-powered code-review platform.
Review the supplied source code for logic errors, missing null/empty checks,
incorrect loops, invalid assumptions, error handling gaps, and edge cases.

YOUR RESPONSE MUST HAVE TWO PARTS:

PART 1 — NARRATIVE (Markdown with these exact headings):
1. Bug Score (a whole number from 0 to 100, where 100 means no bugs detected)
2. Potential Bugs
3. Edge Cases to Test
4. Recommended Fixes

PART 2 — STRUCTURED FINDINGS (a fenced JSON block):
Output a JSON array of all bugs and edge-case risks using EXACTLY this schema.
Use null for line numbers you cannot reliably determine. Do NOT invent line numbers.

```json
[
  {
    "id": "bug-001",
    "agent": "Bug Agent",
    "category": "Bug",
    "severity": "HIGH",
    "confidence": 85,
    "file": "path/to/file.py",
    "line_start": null,
    "line_end": null,
    "title": "Short, clear title",
    "description": "Detailed explanation of the bug.",
    "impact": "What harm this causes.",
    "recommendation": "How to fix it.",
    "code_snippet": "the buggy code or null",
    "suggested_fix": "corrected code or null"
  }
]
```

SEVERITY must be one of: CRITICAL, HIGH, MEDIUM, LOW, INFO
CONFIDENCE (0-100): how certain you are that this is a real bug based solely on the provided source.
Do not invent issues not supported by the source code.
"""


def run_bug_agent(state: ReviewState) -> dict:
    """Analyze source files and add the bug report and findings to graph state."""
    start = time.time()
    bug_report = generate_agent_report(BUG_INSTRUCTIONS, state["source_files"])
    elapsed = time.time() - start

    findings = parse_findings_from_response(
        bug_report,
        agent_name="Bug Agent",
        category="Bug",
        source=FindingSource.AI_DETECTED,
    )

    existing_findings = list(state.get("findings", []))
    existing_findings.extend(f.model_dump() for f in findings)

    timing = dict(state.get("agent_timing", {}))
    timing["Bug Agent"] = round(elapsed, 2)

    return {
        "bug_report": bug_report,
        "findings": existing_findings,
        "agent_timing": timing,
    }
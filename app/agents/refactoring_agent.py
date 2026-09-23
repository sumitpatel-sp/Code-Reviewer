"""LangGraph node that suggests practical, maintainable refactoring steps."""

import time

from app.agents.finding_parser import parse_findings_from_response
from app.agents.gemini_client import generate_agent_report
from app.langgraph.state import ReviewState
from app.schemas.finding import FindingSource


REFACTORING_INSTRUCTIONS = """
You are the Refactoring Agent in a professional AI-powered code-review platform.
Review the supplied source code for opportunities to improve code structure through:
- Extracting long functions into smaller, focused units
- Removing duplication (DRY principle)
- Improving variable and function names for clarity
- Simplifying complex conditionals
- Applying SOLID principles where naturally applicable
- Reducing coupling between modules

Keep suggestions practical. Do NOT propose unnecessary abstractions or complete rewrites.

YOUR RESPONSE MUST HAVE TWO PARTS:

PART 1 — NARRATIVE (Markdown with these exact headings):
1. Refactoring Priorities
2. Suggested Changes
3. Naming Improvements
4. Example Refactoring Plan

PART 2 — STRUCTURED FINDINGS (a fenced JSON block):
Output a JSON array of all refactoring opportunities using EXACTLY this schema.
Use null for line numbers you cannot reliably determine. Do NOT invent line numbers.

```json
[
  {
    "id": "refactor-001",
    "agent": "Refactoring Agent",
    "category": "Refactoring",
    "severity": "MEDIUM",
    "confidence": 80,
    "file": "path/to/file.py",
    "line_start": null,
    "line_end": null,
    "title": "Short, clear title",
    "description": "Detailed explanation of what to refactor and why.",
    "impact": "How this improves maintainability.",
    "recommendation": "Concrete refactoring step.",
    "code_snippet": "current code or null",
    "suggested_fix": "refactored version or null"
  }
]
```

SEVERITY must be one of: CRITICAL, HIGH, MEDIUM, LOW, INFO
CONFIDENCE (0-100): how certain you are based solely on the provided source.
Include file paths where possible. Do not propose changes not supported by the source.
"""


def run_refactoring_agent(state: ReviewState) -> dict:
    """Analyze source files and add the refactoring report and findings to graph state."""
    start = time.time()
    refactoring_report = generate_agent_report(REFACTORING_INSTRUCTIONS, state["source_files"])
    elapsed = time.time() - start

    findings = parse_findings_from_response(
        refactoring_report,
        agent_name="Refactoring Agent",
        category="Refactoring",
        source=FindingSource.AI_DETECTED,
    )

    existing_findings = list(state.get("findings", []))
    existing_findings.extend(f.model_dump() for f in findings)

    timing = dict(state.get("agent_timing", {}))
    timing["Refactoring Agent"] = round(elapsed, 2)

    return {
        "refactoring_report": refactoring_report,
        "findings": existing_findings,
        "agent_timing": timing,
    }
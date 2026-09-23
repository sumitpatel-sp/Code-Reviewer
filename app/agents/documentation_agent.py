"""LangGraph node that evaluates project documentation needs."""

import time

from app.agents.finding_parser import parse_findings_from_response
from app.agents.gemini_client import generate_agent_report
from app.langgraph.state import ReviewState
from app.schemas.finding import FindingSource


DOCUMENTATION_INSTRUCTIONS = """
You are the Documentation Agent in a professional AI-powered code-review platform.
Review the supplied source code and evaluate:
- Missing or inadequate module/class/function docstrings
- Missing README or setup instructions
- Undocumented public APIs
- Confusing or outdated inline comments
- Missing type hints where they would aid understanding
- Missing usage examples for complex functions

Infer only what is supported by the source code.

YOUR RESPONSE MUST HAVE TWO PARTS:

PART 1 — NARRATIVE (Markdown with these exact headings):
1. Project Summary
2. Architecture Summary
3. README Improvement Suggestions
4. Missing Documentation

PART 2 — STRUCTURED FINDINGS (a fenced JSON block):
Output a JSON array of all documentation gaps using EXACTLY this schema.
Use null for line numbers you cannot reliably determine. Do NOT invent line numbers.

```json
[
  {
    "id": "doc-001",
    "agent": "Documentation Agent",
    "category": "Documentation",
    "severity": "LOW",
    "confidence": 85,
    "file": "path/to/file.py",
    "line_start": null,
    "line_end": null,
    "title": "Short, clear title",
    "description": "Detailed explanation of what documentation is missing.",
    "impact": "How the lack of documentation hurts maintainability.",
    "recommendation": "What to add or improve.",
    "code_snippet": "undocumented code or null",
    "suggested_fix": "example docstring or null"
  }
]
```

SEVERITY must be one of: CRITICAL, HIGH, MEDIUM, LOW, INFO
CONFIDENCE (0-100): how certain you are based solely on the provided source.
Do not invent features, dependencies, or deployment details not shown in the source.
"""


def run_documentation_agent(state: ReviewState) -> dict:
    """Analyze source files and add the documentation report and findings to graph state."""
    start = time.time()
    documentation_report = generate_agent_report(DOCUMENTATION_INSTRUCTIONS, state["source_files"])
    elapsed = time.time() - start

    findings = parse_findings_from_response(
        documentation_report,
        agent_name="Documentation Agent",
        category="Documentation",
        source=FindingSource.AI_DETECTED,
    )

    existing_findings = list(state.get("findings", []))
    existing_findings.extend(f.model_dump() for f in findings)

    timing = dict(state.get("agent_timing", {}))
    timing["Documentation Agent"] = round(elapsed, 2)

    return {
        "documentation_report": documentation_report,
        "findings": existing_findings,
        "agent_timing": timing,
    }
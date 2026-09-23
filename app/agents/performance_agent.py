"""LangGraph node that reviews source code for performance improvements."""

import time

from app.agents.finding_parser import parse_findings_from_response
from app.agents.gemini_client import generate_agent_report
from app.langgraph.state import ReviewState
from app.schemas.finding import FindingSource


PERFORMANCE_INSTRUCTIONS = """
You are the Performance Agent in a professional AI-powered code-review platform.
Review the supplied source code for:
- Nested loops and O(n²) or worse algorithms
- Repeated computation that can be cached
- Unnecessary database or file operations inside loops
- Memory leaks or excessive object creation
- Inefficient string concatenation
- Avoidable network calls
- Missing pagination for large data sets

Prefer simple, targeted improvements over premature optimization.

YOUR RESPONSE MUST HAVE TWO PARTS:

PART 1 — NARRATIVE (Markdown with these exact headings):
1. Performance Score (a whole number from 0 to 100)
2. Performance Findings
3. Suggested Improvements
4. Complexity Notes

PART 2 — STRUCTURED FINDINGS (a fenced JSON block):
Output a JSON array of all performance issues using EXACTLY this schema.
Use null for line numbers you cannot reliably determine. Do NOT invent line numbers.

```json
[
  {
    "id": "perf-001",
    "agent": "Performance Agent",
    "category": "Performance",
    "severity": "MEDIUM",
    "confidence": 75,
    "file": "path/to/file.py",
    "line_start": null,
    "line_end": null,
    "title": "Short, clear title",
    "description": "Detailed explanation of the performance issue.",
    "impact": "Estimated performance impact.",
    "recommendation": "How to improve it.",
    "code_snippet": "slow code or null",
    "suggested_fix": "faster alternative or null"
  }
]
```

SEVERITY must be one of: CRITICAL, HIGH, MEDIUM, LOW, INFO
CONFIDENCE (0-100): how certain you are based solely on the provided source.
Do not invent bottlenecks not supported by the source code.
"""


def run_performance_agent(state: ReviewState) -> dict:
    """Analyze source files and add the performance report and findings to graph state."""
    start = time.time()
    performance_report = generate_agent_report(PERFORMANCE_INSTRUCTIONS, state["source_files"])
    elapsed = time.time() - start

    findings = parse_findings_from_response(
        performance_report,
        agent_name="Performance Agent",
        category="Performance",
        source=FindingSource.AI_DETECTED,
    )

    existing_findings = list(state.get("findings", []))
    existing_findings.extend(f.model_dump() for f in findings)

    timing = dict(state.get("agent_timing", {}))
    timing["Performance Agent"] = round(elapsed, 2)

    return {
        "performance_report": performance_report,
        "findings": existing_findings,
        "agent_timing": timing,
    }
"""LangGraph node that reviews source code for common security risks."""

import time

from app.agents.finding_parser import parse_findings_from_response
from app.agents.gemini_client import generate_agent_report
from app.langgraph.state import ReviewState
from app.schemas.finding import FindingSource


SECURITY_INSTRUCTIONS = """
You are the Security Agent in a professional AI-powered code-review platform.
Review the supplied source code for:
- Hardcoded secrets, passwords, API keys (DO NOT reproduce the full secret — redact it)
- SQL injection and unsafe queries
- Path traversal and unsafe file access
- Command injection (subprocess, eval, exec)
- Weak or missing authentication/authorization
- Missing input validation and sanitization
- Insecure deserialization
- SSRF, XSS, CSRF risks

YOUR RESPONSE MUST HAVE TWO PARTS:

PART 1 — NARRATIVE (Markdown with these exact headings):
1. Security Score (a whole number from 0 to 100)
2. Security Findings
3. Recommended Fixes
4. Positive Security Practices

PART 2 — STRUCTURED FINDINGS (a fenced JSON block):
Output a JSON array of all security issues using EXACTLY this schema.
For discovered secrets: redact the value in code_snippet (replace with [REDACTED]).
Use null for line numbers you cannot reliably determine. Do NOT invent line numbers.

```json
[
  {
    "id": "sec-001",
    "agent": "Security Agent",
    "category": "Security",
    "severity": "CRITICAL",
    "confidence": 90,
    "file": "path/to/file.py",
    "line_start": null,
    "line_end": null,
    "title": "Short, clear title",
    "description": "Detailed explanation without exposing secrets.",
    "impact": "What harm this causes.",
    "recommendation": "How to fix it.",
    "code_snippet": "redacted code context or null",
    "suggested_fix": "safe alternative code or null"
  }
]
```

SEVERITY must be one of: CRITICAL, HIGH, MEDIUM, LOW, INFO
CONFIDENCE (0-100): how certain you are based solely on the provided source.
Do not invent vulnerabilities not supported by the source. Do not expose full secret values.
"""


def run_security_agent(state: ReviewState) -> dict:
    """Analyze source files and add the security report and findings to graph state."""
    start = time.time()
    security_report = generate_agent_report(SECURITY_INSTRUCTIONS, state["source_files"])
    elapsed = time.time() - start

    findings = parse_findings_from_response(
        security_report,
        agent_name="Security Agent",
        category="Security",
        source=FindingSource.AI_DETECTED,
    )

    existing_findings = list(state.get("findings", []))
    existing_findings.extend(f.model_dump() for f in findings)

    timing = dict(state.get("agent_timing", {}))
    timing["Security Agent"] = round(elapsed, 2)

    return {
        "security_report": security_report,
        "findings": existing_findings,
        "agent_timing": timing,
    }
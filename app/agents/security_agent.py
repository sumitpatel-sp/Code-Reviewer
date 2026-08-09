"""LangGraph node that reviews source code for common security risks."""

from app.agents.gemini_client import generate_agent_report
from app.langgraph.state import ReviewState


SECURITY_INSTRUCTIONS = """
You are the Security Agent in a software code-review platform.
Review the supplied source code for hardcoded passwords, secrets, API keys,
unsafe SQL queries, unsafe file access, command injection, weak authentication,
and missing input validation. Do not reveal a discovered secret in full; redact it.
Return Markdown with these exact headings:
1. Security Score (a whole number from 0 to 100)
2. Security Findings
3. Recommended Fixes
4. Positive Security Practices
For each finding, include severity (high, medium, or low), file path, and explanation.
Do not invent vulnerabilities that are not supported by the source.
"""


def run_security_agent(state: ReviewState) -> dict[str, str]:
    """Analyze source files and add the security report to the graph state."""
    security_report = generate_agent_report(SECURITY_INSTRUCTIONS, state["source_files"])
    return {"security_report": security_report}
"""LangGraph node that identifies likely bugs and unhandled edge cases."""

from app.agents.gemini_client import generate_agent_report
from app.langgraph.state import ReviewState


BUG_INSTRUCTIONS = """
You are the Bug Detection Agent in a software code-review platform.
Review the supplied source code for logic errors, missing null or empty checks,
incorrect loops, invalid assumptions, error handling gaps, and edge cases.
Return Markdown with these exact headings:
1. Bug Score (a whole number from 0 to 100, where higher means fewer risks)
2. Potential Bugs
3. Edge Cases to Test
4. Recommended Fixes
For each potential bug, include severity (high, medium, or low), a file path,
and a short explanation. Do not invent issues not supported by the source.
"""


def run_bug_agent(state: ReviewState) -> dict[str, str]:
    """Analyze source files and add the bug report to the graph state."""
    bug_report = generate_agent_report(BUG_INSTRUCTIONS, state["source_files"])
    return {"bug_report": bug_report}
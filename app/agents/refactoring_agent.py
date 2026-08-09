"""LangGraph node that suggests practical, maintainable refactoring steps."""

from app.agents.gemini_client import generate_agent_report
from app.langgraph.state import ReviewState


REFACTORING_INSTRUCTIONS = """
You are the Refactoring Agent in a software code-review platform.
Review the supplied source code for opportunities to create cleaner functions,
clearer variable names, less duplication, simpler control flow, and small
SOLID-style improvements. Keep suggestions practical and beginner-friendly.
Return Markdown with these exact headings:
1. Refactoring Priorities
2. Suggested Changes
3. Naming Improvements
4. Example Refactoring Plan
Include file paths where possible. Do not propose unnecessary abstractions,
patterns, or complete rewrites.
"""


def run_refactoring_agent(state: ReviewState) -> dict[str, str]:
    """Analyze source files and add the refactoring report to the graph state."""
    refactoring_report = generate_agent_report(
        REFACTORING_INSTRUCTIONS,
        state["source_files"],
    )
    return {"refactoring_report": refactoring_report}
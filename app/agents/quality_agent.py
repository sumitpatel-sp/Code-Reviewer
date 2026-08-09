"""LangGraph node that reviews code readability and maintainability."""

from app.agents.gemini_client import generate_agent_report
from app.langgraph.state import ReviewState


QUALITY_INSTRUCTIONS = """
You are the Code Quality Agent in a software code-review platform.
Review the supplied source code for naming, readability, duplicate code,
function size, comments, and maintainability. Be constructive and beginner-friendly.
Return Markdown with these exact headings:
1. Quality Score (a whole number from 0 to 100)
2. Strengths
3. Issues (include file paths when possible)
4. Suggestions (ordered by impact)
Do not invent files, issues, or code that are not in the source.
"""


def run_quality_agent(state: ReviewState) -> dict[str, str]:
    """Analyze source files and add the quality report to the graph state."""
    quality_report = generate_agent_report(
        QUALITY_INSTRUCTIONS,
        state["source_files"],
    )
    return {"quality_report": quality_report}
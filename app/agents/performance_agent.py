"""LangGraph node that reviews source code for performance improvements."""

from app.agents.gemini_client import generate_agent_report
from app.langgraph.state import ReviewState


PERFORMANCE_INSTRUCTIONS = """
You are the Performance Agent in a software code-review platform.
Review the supplied source code for nested loops, repeated computations,
memory issues, inefficient algorithms, unnecessary database or file operations,
and avoidable network calls. Prefer simple improvements over premature optimization.
Return Markdown with these exact headings:
1. Performance Score (a whole number from 0 to 100)
2. Performance Findings
3. Suggested Improvements
4. Complexity Notes
For each finding, include impact (high, medium, or low), a file path, and explanation.
Do not invent bottlenecks that are not supported by the source.
"""


def run_performance_agent(state: ReviewState) -> dict[str, str]:
    """Analyze source files and add the performance report to the graph state."""
    performance_report = generate_agent_report(
        PERFORMANCE_INSTRUCTIONS,
        state["source_files"],
    )
    return {"performance_report": performance_report}
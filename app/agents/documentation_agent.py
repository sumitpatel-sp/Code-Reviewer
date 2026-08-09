"""LangGraph node that evaluates project documentation needs."""

from app.agents.gemini_client import generate_agent_report
from app.langgraph.state import ReviewState


DOCUMENTATION_INSTRUCTIONS = """
You are the Documentation Agent in a software code-review platform.
Review the supplied source code and create a beginner-friendly documentation report.
Infer only what is supported by the source code.
Return Markdown with these exact headings:
1. Project Summary
2. Architecture Summary
3. README Improvement Suggestions
4. Missing Documentation
Explain important components and their relationships in plain language.
Do not invent features, dependencies, or deployment details not shown in the source.
"""


def run_documentation_agent(state: ReviewState) -> dict[str, str]:
    """Analyze source files and add the documentation report to graph state."""
    documentation_report = generate_agent_report(
        DOCUMENTATION_INSTRUCTIONS,
        state["source_files"],
    )
    return {"documentation_report": documentation_report}
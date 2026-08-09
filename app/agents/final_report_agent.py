"""LangGraph node that combines specialized reviews into one final report."""

import re

from app.agents.gemini_client import generate_text
from app.langgraph.state import ReviewState


FINAL_REPORT_INSTRUCTIONS = """
You are the Final Report Agent in a software code-review platform.
Combine the specialized reports below into one accurate, beginner-friendly Markdown report.
Return these exact headings:
1. Overall Score: <whole number from 0 to 100>
2. Quality Score
3. Security Score
4. Performance Score
5. Bug Score
6. Final Summary
7. Highest-Priority Next Steps
Do not add findings that are absent from the specialized reports. Reconcile duplicates.
"""


def extract_overall_score(final_summary: str) -> float:
    """Read the required overall score from the final agent's Markdown response."""
    score_match = re.search(r"Overall Score:\s*(\d{1,3})", final_summary, re.IGNORECASE)
    if score_match is None:
        return 0.0
    return float(min(int(score_match.group(1)), 100))


def run_final_report_agent(state: ReviewState) -> dict[str, str | float]:
    """Combine all specialized reports into final summary and score fields."""
    reports = "\n\n".join(
        f"## {title}\n{state.get(field, 'No report available.')}"
        for title, field in (
            ("Code Quality Report", "quality_report"),
            ("Bug Detection Report", "bug_report"),
            ("Security Report", "security_report"),
            ("Performance Report", "performance_report"),
            ("Refactoring Report", "refactoring_report"),
            ("Documentation Report", "documentation_report"),
        )
    )
    final_summary = generate_text(f"{FINAL_REPORT_INSTRUCTIONS}\n\nSPECIALIZED REPORTS:\n{reports}")
    return {
        "overall_score": extract_overall_score(final_summary),
        "final_summary": final_summary,
    }
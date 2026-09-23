"""LangGraph node that combines specialized reviews into one final structured report."""

import logging
import re
import time

from app.agents.finding_parser import extract_score_from_text
from app.agents.gemini_client import generate_text
from app.langgraph.state import ReviewState


logger = logging.getLogger(__name__)

# Maximum characters per individual sub-report before truncation.
# Keeps the combined prompt well under Gemini's 1M token limit.
_MAX_CHARS_PER_REPORT = 25_000
_MAX_TOTAL_CHARS = 90_000


FINAL_REPORT_INSTRUCTIONS = """
You are the Final Report Agent in a professional AI-powered code-review platform.
Combine the specialized reports below into one accurate, structured Markdown report.

Return EXACTLY these headings in order:

# AI Code Review Report

## 1. Overall Score: <whole number 0-100>

## 2. Score Breakdown
- Quality Score: <0-100>
- Security Score: <0-100>
- Performance Score: <0-100>
- Maintainability Score: <0-100>
- Testing Score: <0-100>

## 3. Executive Summary
<2-3 paragraph summary of the most important findings>

## 4. Top Priority Issues
<List the 3–5 most critical issues found across all agents, with file references>

## 5. Findings by Category
<Summarize key findings per category: Security, Bugs, Quality, Performance, Refactoring, Testing, Documentation>

## 6. Agent Summary
| Agent | Findings | Status |
|-------|----------|--------|
<table row per agent>

## 7. Prioritized Action Plan
1. <Most urgent action>
2. <Second action>
...

## 8. Positive Observations
<What the code does well>

RULES:
- Do not add findings absent from the specialized reports.
- Reconcile duplicate issues: mention once.
- Be specific: reference file names and function names found in the source.
- Scores should reflect the combined picture from all agents.
"""


def _extract_score(text: str, label: str) -> float:
    """Extract a labelled score from the final report narrative."""
    pattern = rf"{re.escape(label)}[:\s]+(\d{{1,3}})"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return float(min(int(match.group(1)), 100))
    return 0.0


def _truncate(text: str, max_chars: int) -> str:
    """Truncate long text, appending a notice so the LLM knows it is clipped."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[... report truncated for length ...]"


def _build_fallback_summary(state: ReviewState) -> str:
    """Build a structured fallback summary from state fields when Gemini call fails."""
    q_score = _extract_score(state.get("quality_report", ""), "Quality Score")
    s_score = _extract_score(state.get("security_report", ""), "Security Score")
    p_score = _extract_score(state.get("performance_report", ""), "Performance Score")

    valid_scores = [s for s in [q_score, s_score, p_score] if s > 0]
    overall = round(sum(valid_scores) / len(valid_scores), 1) if valid_scores else 75.0

    lines = ["# AI Code Review Report\n"]
    lines.append(f"## 1. Overall Score: {int(overall)}\n")
    lines.append("## 2. Score Breakdown\n")
    lines.append(f"- Quality Score: {int(q_score or overall)}\n")
    lines.append(f"- Security Score: {int(s_score or overall)}\n")
    lines.append(f"- Performance Score: {int(p_score or overall)}\n")
    lines.append(f"- Maintainability Score: {int(q_score or overall)}\n")
    lines.append(f"- Testing Score: {int(overall)}\n")
    lines.append("\n## 3. Executive Summary\n")
    lines.append(
        "All specialized code review agents completed their analysis. "
        "The consolidated report below summarizes findings across code quality, security, "
        "performance, and maintainability.\n"
    )
    for title, field in (
        ("Code Quality", "quality_report"),
        ("Bug Detection", "bug_report"),
        ("Security", "security_report"),
        ("Performance", "performance_report"),
        ("Refactoring", "refactoring_report"),
        ("Documentation", "documentation_report"),
    ):
        content = state.get(field, "")
        if content:
            lines.append(f"\n## {title}\n{_truncate(content, 4000)}\n")
    return "\n".join(lines)


def run_final_report_agent(state: ReviewState) -> dict:
    """Combine all specialized reports into a final structured summary."""
    start = time.time()

    sub_reports = []
    for title, field in (
        ("Code Quality Report", "quality_report"),
        ("Bug Detection Report", "bug_report"),
        ("Security Report", "security_report"),
        ("Performance Report", "performance_report"),
        ("Refactoring Report", "refactoring_report"),
        ("Documentation Report", "documentation_report"),
    ):
        content = state.get(field, "No report available.")
        truncated = _truncate(content, _MAX_CHARS_PER_REPORT)
        sub_reports.append(f"## {title}\n{truncated}")

    reports = "\n\n".join(sub_reports)
    reports = _truncate(reports, _MAX_TOTAL_CHARS)

    prompt = f"{FINAL_REPORT_INSTRUCTIONS}\n\nSPECIALIZED REPORTS:\n{reports}"
    logger.info("Final Report Agent: prompt length %d chars", len(prompt))

    try:
        final_summary = generate_text(prompt)
    except Exception as exc:
        logger.error("Final Report Agent failed to call Gemini: %s", exc)
        final_summary = _build_fallback_summary(state)

    elapsed = time.time() - start

    # Extract granular scores from the final narrative
    overall_score = _extract_score(final_summary, "Overall Score")
    quality_score = _extract_score(final_summary, "Quality Score")
    security_score = _extract_score(final_summary, "Security Score")
    performance_score = _extract_score(final_summary, "Performance Score")
    maintainability_score = _extract_score(final_summary, "Maintainability Score")
    testing_score = _extract_score(final_summary, "Testing Score")

    # Fall back to averaging other scores when overall_score could not be extracted
    if overall_score == 0.0:
        valid = [s for s in [quality_score, security_score, performance_score,
                              maintainability_score, testing_score] if s > 0]
        if valid:
            overall_score = round(sum(valid) / len(valid), 1)

    timing = dict(state.get("agent_timing", {}))
    timing["Final Report Agent"] = round(elapsed, 2)

    logger.info(
        "Final Report Agent completed in %.1fs — overall score %.1f",
        elapsed, overall_score,
    )

    return {
        "overall_score": overall_score,
        "quality_score": quality_score,
        "security_score": security_score,
        "performance_score": performance_score,
        "maintainability_score": maintainability_score,
        "testing_score": testing_score,
        "final_summary": final_summary,
        "agent_timing": timing,
    }
"""LangGraph workflow for the multi-agent code-review process."""

from langgraph.graph import END, START, StateGraph

from app.agents.bug_agent import run_bug_agent
from app.agents.documentation_agent import run_documentation_agent
from app.agents.final_report_agent import run_final_report_agent
from app.agents.performance_agent import run_performance_agent
from app.agents.quality_agent import run_quality_agent
from app.agents.refactoring_agent import run_refactoring_agent
from app.agents.security_agent import run_security_agent
from app.langgraph.state import ReviewState


import time


def validate_source_files(state: ReviewState) -> ReviewState:
    """Ensure the uploaded repository contains supported source files."""
    if not state.get("source_files"):
        raise ValueError("The uploaded ZIP does not contain supported source files.")
    return state


def pace_requests(state: ReviewState) -> ReviewState:
    """Pause briefly between agents to avoid hitting Gemini rate limits."""
    time.sleep(5)
    return state


def build_review_graph():
    """Create the readable, sequential workflow used for every code review."""
    workflow = StateGraph(ReviewState)
    workflow.add_node("validate_source_files", validate_source_files)
    workflow.add_node("quality_review", run_quality_agent)
    workflow.add_node("pace_1", pace_requests)
    workflow.add_node("bug_detection", run_bug_agent)
    workflow.add_node("pace_2", pace_requests)
    workflow.add_node("security_review", run_security_agent)
    workflow.add_node("pace_3", pace_requests)
    workflow.add_node("performance_review", run_performance_agent)
    workflow.add_node("pace_4", pace_requests)
    workflow.add_node("refactoring_review", run_refactoring_agent)
    workflow.add_node("pace_5", pace_requests)
    workflow.add_node("documentation_review", run_documentation_agent)
    workflow.add_node("pace_6", pace_requests)
    workflow.add_node("final_report", run_final_report_agent)

    workflow.add_edge(START, "validate_source_files")
    workflow.add_edge("validate_source_files", "quality_review")
    workflow.add_edge("quality_review", "pace_1")
    workflow.add_edge("pace_1", "bug_detection")
    workflow.add_edge("bug_detection", "pace_2")
    workflow.add_edge("pace_2", "security_review")
    workflow.add_edge("security_review", "pace_3")
    workflow.add_edge("pace_3", "performance_review")
    workflow.add_edge("performance_review", "pace_4")
    workflow.add_edge("pace_4", "refactoring_review")
    workflow.add_edge("refactoring_review", "pace_5")
    workflow.add_edge("pace_5", "documentation_review")
    workflow.add_edge("documentation_review", "pace_6")
    workflow.add_edge("pace_6", "final_report")
    workflow.add_edge("final_report", END)
    return workflow.compile()
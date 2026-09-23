"""LangGraph workflow for the multi-agent code-review process.

Workflow order:
  1. validate_source_files — ensure supported files exist
  2. static_analysis — deterministic AST/Radon/Bandit analysis (new)
  3. semgrep_analysis — cross-language Semgrep static analysis (new)
  4. feature_extraction — extract ML features (new)
  5. ml_risk_prediction — predict defect/maintenance risk (new)
  6. quality_review — LLM quality agent
  7. pace_1 — rate-limit pause
  8. bug_detection — LLM bug agent
  9. pace_2 — rate-limit pause
  10. security_review — LLM security agent (Bandit + Semgrep findings already in state)
  11. pace_3 — rate-limit pause
  12. performance_review — LLM performance agent
  13. pace_4 — rate-limit pause
  14. refactoring_review — LLM refactoring agent
  15. pace_5 — rate-limit pause
  16. documentation_review — LLM documentation agent
  17. pace_6 — rate-limit pause
  18. aggregate_findings — deduplication + confidence boosting (new)
  19. final_report — LLM final report agent
"""

import logging
import time

from langgraph.graph import END, START, StateGraph

from app.agents.bug_agent import run_bug_agent
from app.agents.documentation_agent import run_documentation_agent
from app.agents.final_report_agent import run_final_report_agent
from app.agents.performance_agent import run_performance_agent
from app.agents.quality_agent import run_quality_agent
from app.agents.refactoring_agent import run_refactoring_agent
from app.agents.security_agent import run_security_agent
from app.langgraph.state import ReviewState
from app.services.finding_aggregator import deduplicate_and_aggregate
from app.static_analysis.analyzer import analyze_all_files
from app.static_analysis.feature_extractor import extract_features
from app.static_analysis.semgrep_runner import run_semgrep
from app.ml.model import predict_risk


logger = logging.getLogger(__name__)


def validate_source_files(state: ReviewState) -> ReviewState:
    """Ensure the uploaded repository contains supported source files."""
    if not state.get("source_files"):
        raise ValueError("The uploaded ZIP does not contain supported source files.")
    return state


def run_static_analysis(state: ReviewState) -> dict:
    """Run deterministic static analysis before sending code to LLM agents."""
    start = time.time()
    source_files = state.get("source_files", {})

    try:
        results = analyze_all_files(source_files)
    except Exception as exc:
        logger.warning("Static analysis failed: %s", exc)
        results = {"findings": [], "per_file_metrics": {}, "aggregate_metrics": {}}

    elapsed = time.time() - start
    timing = dict(state.get("agent_timing", {}))
    timing["Static Analysis"] = round(elapsed, 2)

    logger.info(
        "Static analysis: %d findings in %.1fs",
        len(results.get("findings", [])), elapsed,
    )

    return {
        "static_analysis_results": results,
        "findings": list(results.get("findings", [])),
        "agent_timing": timing,
    }


def run_semgrep_analysis(state: ReviewState) -> dict:
    """Run Semgrep cross-language static analysis and merge findings into state.

    Uses the ``extraction_path`` stored in state by the upload router.  If the
    path is absent or Semgrep is unavailable the node returns the unchanged
    state so the pipeline continues unaffected.
    """
    start = time.time()
    extraction_path_str: str | None = state.get("extraction_path")
    source_files: dict = state.get("source_files", {})

    semgrep_findings: list[dict] = []
    if extraction_path_str:
        from pathlib import Path as _Path
        try:
            sg_results = run_semgrep(
                _Path(extraction_path_str),
                source_files,
            )
            semgrep_findings = [f.model_dump() for f in sg_results]
        except Exception as exc:  # pragma: no cover
            logger.warning("Semgrep node raised unexpectedly: %s", exc)
    else:
        logger.debug("Semgrep node: no extraction_path in state, skipping.")

    elapsed = time.time() - start
    timing = dict(state.get("agent_timing", {}))
    timing["Semgrep"] = round(elapsed, 2)

    existing_findings = list(state.get("findings", []))
    existing_findings.extend(semgrep_findings)

    logger.info(
        "Semgrep node: %d finding(s) added in %.1fs.",
        len(semgrep_findings), elapsed,
    )
    return {
        "findings": existing_findings,
        "agent_timing": timing,
    }


def run_feature_extraction(state: ReviewState) -> dict:
    """Extract ML feature vector from static analysis results and LLM findings."""
    static_results = state.get("static_analysis_results", {})
    llm_findings = [
        f for f in state.get("findings", [])
        if f.get("source") != "static_analysis"
    ]

    features = extract_features(
        aggregate_metrics=static_results.get("aggregate_metrics", {}),
        per_file_metrics=static_results.get("per_file_metrics", {}),
        static_findings=list(static_results.get("findings", [])),
        llm_findings=llm_findings,
    )
    return {"ml_features": features}


def run_ml_prediction(state: ReviewState) -> dict:
    """Run the ML risk model on the extracted feature vector."""
    features = state.get("ml_features", {})
    try:
        prediction = predict_risk(features)
    except Exception as exc:
        logger.warning("ML prediction failed: %s", exc)
        prediction = {
            "defect_probability": 0.0,
            "maintenance_risk": 0.0,
            "review_priority": "UNKNOWN",
            "human_review_recommended": False,
            "top_risk_factors": [],
            "shap_values": {},
            "model_version": "1.0",
            "disclaimer": "ML prediction unavailable.",
        }
    return {"ml_risk_prediction": prediction}


def run_finding_aggregator(state: ReviewState) -> dict:
    """Deduplicate and merge findings from all agents + static analysis."""
    all_findings = state.get("findings", [])
    merged = deduplicate_and_aggregate(all_findings)
    return {"findings": [f.model_dump() for f in merged]}


def pace_requests(state: ReviewState) -> ReviewState:
    """Pause briefly between agents to avoid hitting Gemini rate limits."""
    time.sleep(5)
    return state


def build_review_graph():
    """Create the extended LangGraph workflow for the upgraded code review."""
    workflow = StateGraph(ReviewState)

    # Nodes
    workflow.add_node("validate_source_files", validate_source_files)
    workflow.add_node("static_analysis", run_static_analysis)
    workflow.add_node("semgrep_analysis", run_semgrep_analysis)
    workflow.add_node("feature_extraction", run_feature_extraction)
    workflow.add_node("ml_risk_prediction", run_ml_prediction)
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
    workflow.add_node("aggregate_findings", run_finding_aggregator)
    workflow.add_node("final_report", run_final_report_agent)

    # Edges
    workflow.add_edge(START, "validate_source_files")
    workflow.add_edge("validate_source_files", "static_analysis")
    workflow.add_edge("static_analysis", "semgrep_analysis")
    workflow.add_edge("semgrep_analysis", "feature_extraction")
    workflow.add_edge("feature_extraction", "ml_risk_prediction")
    workflow.add_edge("ml_risk_prediction", "quality_review")
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
    workflow.add_edge("pace_6", "aggregate_findings")
    workflow.add_edge("aggregate_findings", "final_report")
    workflow.add_edge("final_report", END)

    return workflow.compile()
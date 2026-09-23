"""Extract software-engineering features for ML code risk prediction.

Features are computed from static analysis results and (optionally) from
LLM findings. They are mapped to the feature space expected by the trained
XGBoost model.

No git history features are included because git history is not reliably
available for uploaded ZIP files.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# The canonical feature order expected by the trained model.
# IMPORTANT: This list must match the column order used during training.
MODEL_FEATURE_NAMES: list[str] = [
    "loc",
    "num_functions",
    "num_classes",
    "num_imports",
    "cyclomatic_complexity_avg",
    "max_nesting_depth",
    "avg_function_length",
    "comment_ratio",
    "num_static_findings",
    "num_llm_findings",
    "severity_weighted_score",
    "code_lines",
]


def _severity_weight(severity: str) -> int:
    """Map a severity string to a numeric weight for the weighted finding score."""
    weights = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}
    return weights.get(severity.upper(), 1)


def extract_features(
    aggregate_metrics: dict,
    per_file_metrics: dict[str, dict],
    static_findings: list[dict],
    llm_findings: list[dict],
) -> dict[str, float]:
    """Compute the feature vector for the ML risk model.

    Parameters
    ----------
    aggregate_metrics:
        Combined metrics from static_analysis.analyze_all_files().
    per_file_metrics:
        Per-file metrics dict (used to compute averages).
    static_findings:
        Structured findings from static analysis (dicts).
    llm_findings:
        Structured findings from LLM agents (dicts).

    Returns
    -------
    dict mapping feature name → float value, ordered to match MODEL_FEATURE_NAMES.
    """
    # Aggregate LOC and structural metrics
    loc = float(aggregate_metrics.get("total_loc", 0))
    num_functions = float(aggregate_metrics.get("total_functions", 0))
    num_classes = float(aggregate_metrics.get("total_classes", 0))
    num_imports = float(aggregate_metrics.get("total_imports", 0))
    avg_cc = float(aggregate_metrics.get("avg_cyclomatic_complexity", 0.0))
    num_static = float(len(static_findings))
    num_llm = float(len(llm_findings))
    code_lines = float(sum(m.get("code_lines", 0) for m in per_file_metrics.values()))

    # Max nesting depth across all files
    nesting_values = [m.get("max_nesting_depth", 0) for m in per_file_metrics.values()]
    max_nesting = float(max(nesting_values, default=0))

    # Average function length across all files
    func_lengths = [m.get("avg_function_length", 0.0) for m in per_file_metrics.values() if m.get("avg_function_length")]
    avg_func_length = float(sum(func_lengths) / len(func_lengths)) if func_lengths else 0.0

    # Comment ratio: average across all files
    comment_ratios = [m.get("comment_ratio", 0.0) for m in per_file_metrics.values()]
    avg_comment_ratio = float(sum(comment_ratios) / len(comment_ratios)) if comment_ratios else 0.0

    # Severity-weighted finding count (combines static + LLM)
    all_findings = static_findings + llm_findings
    severity_weighted = float(
        sum(_severity_weight(f.get("severity", "LOW")) for f in all_findings)
    )

    features = {
        "loc": loc,
        "num_functions": num_functions,
        "num_classes": num_classes,
        "num_imports": num_imports,
        "cyclomatic_complexity_avg": avg_cc,
        "max_nesting_depth": max_nesting,
        "avg_function_length": avg_func_length,
        "comment_ratio": avg_comment_ratio,
        "num_static_findings": num_static,
        "num_llm_findings": num_llm,
        "severity_weighted_score": severity_weighted,
        "code_lines": code_lines,
    }

    logger.debug("Extracted ML features: %s", features)
    return features


def features_to_vector(features: dict[str, float]) -> list[float]:
    """Convert a features dict to an ordered list matching MODEL_FEATURE_NAMES."""
    return [features.get(name, 0.0) for name in MODEL_FEATURE_NAMES]

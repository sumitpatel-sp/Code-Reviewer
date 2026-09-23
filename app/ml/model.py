"""XGBoost-based code risk prediction model.

DATASET: KC1 from the PROMISE Software Engineering Repository
  - Source: http://promise.site.uottawa.ca/SERepository/datasets-page.html
  - Reference: "Defect Prediction Using Software Metrics" (NASA MDP datasets)
  - KC1 contains 2109 Java modules with CK object-oriented metrics and binary
    defect labels from a NASA flight software project.
  - License: Public domain for research use.

MODEL: XGBoost binary classifier
  - Target: defect_count > 0 → binary defective/not-defective
  - Features: CK metrics mapped to our extracted code metrics
  - Evaluated with: Precision, Recall, F1, ROC-AUC, PR-AUC

LIMITATIONS:
  - Trained on Java (KC1) but applied to mixed-language repositories.
  - Predicts statistical risk based on structural code metrics, not actual defects.
  - Should be interpreted as "this type of code historically tends to have more defects",
    not as a guarantee that defects exist.
  - Do not use this output to make deployment decisions without human review.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

_MODEL_ARTIFACTS_DIR = Path(__file__).parent / "model_artifacts"
_MODEL_PATH = _MODEL_ARTIFACTS_DIR / "risk_model.joblib"
_SCALER_PATH = _MODEL_ARTIFACTS_DIR / "scaler.joblib"

# Lazy-loaded to avoid startup cost when the model is not yet trained
_model = None
_scaler = None


def _load_model():
    """Load the trained XGBoost model and scaler from disk."""
    global _model, _scaler
    if _model is not None:
        return _model, _scaler

    try:
        import joblib
        if _MODEL_PATH.exists() and _SCALER_PATH.exists():
            _model = joblib.load(_MODEL_PATH)
            _scaler = joblib.load(_SCALER_PATH)
            logger.info("ML risk model loaded from %s", _MODEL_PATH)
        else:
            logger.warning(
                "ML model artifacts not found at %s. "
                "Run app/ml/train.py to train the model. "
                "Falling back to heuristic risk prediction.",
                _MODEL_ARTIFACTS_DIR,
            )
    except Exception as exc:
        logger.warning("Failed to load ML model: %s. Using heuristic fallback.", exc)

    return _model, _scaler


def _heuristic_risk(features: dict[str, float]) -> tuple[float, float]:
    """Rule-based fallback when the trained model is unavailable.

    Returns (defect_probability, maintenance_risk) in [0, 1].
    This is NOT a trained model — it is a deterministic heuristic
    derived from known software engineering thresholds.
    """
    score = 0.0
    max_score = 0.0

    # High cyclomatic complexity
    cc = features.get("cyclomatic_complexity_avg", 0.0)
    max_score += 25
    if cc >= 20:
        score += 25
    elif cc >= 10:
        score += 15
    elif cc >= 5:
        score += 5

    # Large files
    loc = features.get("loc", 0)
    max_score += 20
    if loc >= 1000:
        score += 20
    elif loc >= 500:
        score += 10
    elif loc >= 200:
        score += 5

    # Security/bug findings
    severity_weighted = features.get("severity_weighted_score", 0.0)
    max_score += 25
    if severity_weighted >= 20:
        score += 25
    elif severity_weighted >= 10:
        score += 15
    elif severity_weighted >= 5:
        score += 8

    # Low comment ratio
    comment_ratio = features.get("comment_ratio", 0.0)
    max_score += 15
    if comment_ratio < 0.05:
        score += 15
    elif comment_ratio < 0.1:
        score += 8

    # Deep nesting
    nesting = features.get("max_nesting_depth", 0)
    max_score += 15
    if nesting >= 5:
        score += 15
    elif nesting >= 3:
        score += 8

    defect_prob = score / max_score if max_score > 0 else 0.0
    # Maintenance risk is slightly correlated but weighted differently
    maintenance_risk = min(
        (
            features.get("cyclomatic_complexity_avg", 0) / 30 * 0.4
            + (1 - features.get("comment_ratio", 0)) * 0.3
            + features.get("avg_function_length", 0) / 100 * 0.3
        ),
        1.0,
    )
    return round(defect_prob, 3), round(maintenance_risk, 3)


def _compute_top_risk_factors(features: dict[str, float], shap_values: dict[str, float]) -> list[str]:
    """Return human-readable top risk factors based on SHAP values or feature heuristics."""
    if shap_values:
        # Sort by absolute SHAP impact and return the top 5
        sorted_factors = sorted(shap_values.items(), key=lambda x: abs(x[1]), reverse=True)[:5]
        factor_descriptions = {
            "cyclomatic_complexity_avg": "High cyclomatic complexity",
            "loc": "Large file size (many lines of code)",
            "severity_weighted_score": "High-severity issues detected",
            "num_static_findings": "Multiple static analysis issues",
            "num_llm_findings": "Multiple AI-detected issues",
            "max_nesting_depth": "Deep code nesting",
            "avg_function_length": "Long function bodies",
            "comment_ratio": "Low comment/documentation ratio",
            "num_imports": "High number of dependencies",
            "num_functions": "Large number of functions",
            "num_classes": "Large number of classes",
            "code_lines": "Large code base",
        }
        return [
            factor_descriptions.get(name, name.replace("_", " ").title())
            for name, _ in sorted_factors
            if abs(_) > 0.01
        ]

    # Fallback: use threshold-based heuristics
    factors = []
    if features.get("cyclomatic_complexity_avg", 0) >= 10:
        factors.append("High cyclomatic complexity")
    if features.get("loc", 0) >= 500:
        factors.append("Large file size")
    if features.get("severity_weighted_score", 0) >= 10:
        factors.append("High-severity findings detected")
    if features.get("comment_ratio", 0) < 0.08:
        factors.append("Low documentation/comment ratio")
    if features.get("max_nesting_depth", 0) >= 4:
        factors.append("Deep code nesting")
    if features.get("avg_function_length", 0) >= 50:
        factors.append("Long function bodies")
    if features.get("num_imports", 0) >= 20:
        factors.append("High number of dependencies")
    return factors[:5] if factors else ["Metrics within acceptable ranges"]


def predict_risk(features: dict[str, float]) -> dict:
    """Predict defect probability and maintenance risk from code metrics.

    Parameters
    ----------
    features:
        Feature dict from feature_extractor.extract_features().

    Returns
    -------
    dict with keys: defect_probability, maintenance_risk, review_priority,
    human_review_recommended, top_risk_factors, shap_values, model_version,
    disclaimer, model_used.
    """
    from app.static_analysis.feature_extractor import MODEL_FEATURE_NAMES, features_to_vector

    model, scaler = _load_model()
    shap_values: dict[str, float] = {}
    model_used = "heuristic_fallback"

    if model is not None and scaler is not None:
        try:
            import numpy as np
            feature_vector = features_to_vector(features)
            X = np.array(feature_vector).reshape(1, -1)
            X_scaled = scaler.transform(X)

            defect_prob = float(model.predict_proba(X_scaled)[0][1])
            model_used = "xgboost_kc1"

            # Maintenance risk: use heuristic since it's not a trained target
            _, maintenance_risk = _heuristic_risk(features)

            # SHAP explanation
            try:
                import shap
                explainer = shap.TreeExplainer(model)
                shap_raw = explainer.shap_values(X_scaled)
                # For binary classification, shap_values may be list[array] or array
                if isinstance(shap_raw, list):
                    values = shap_raw[1][0]
                else:
                    values = shap_raw[0]
                shap_values = {
                    name: round(float(val), 4)
                    for name, val in zip(MODEL_FEATURE_NAMES, values)
                }
            except Exception as exc:
                logger.debug("SHAP explanation failed: %s", exc)

        except Exception as exc:
            logger.warning("ML model prediction failed: %s. Using heuristic.", exc)
            defect_prob, maintenance_risk = _heuristic_risk(features)
    else:
        defect_prob, maintenance_risk = _heuristic_risk(features)

    # Determine review priority
    if defect_prob >= 0.65:
        review_priority = "HIGH"
    elif defect_prob >= 0.35:
        review_priority = "MEDIUM"
    else:
        review_priority = "LOW"

    human_review = defect_prob >= 0.50 or maintenance_risk >= 0.60

    top_factors = _compute_top_risk_factors(features, shap_values)

    return {
        "defect_probability": round(defect_prob, 3),
        "maintenance_risk": round(maintenance_risk, 3),
        "review_priority": review_priority,
        "human_review_recommended": human_review,
        "top_risk_factors": top_factors,
        "shap_values": shap_values,
        "model_version": "1.0",
        "model_used": model_used,
        "disclaimer": (
            "Risk prediction is based on statistical patterns in code metrics from the KC1 "
            "NASA defect dataset. It indicates likelihood of issues, not certainty. "
            "Always apply human judgment before acting on these results."
        ),
    }

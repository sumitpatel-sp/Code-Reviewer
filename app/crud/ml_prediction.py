"""CRUD operations for ML risk predictions."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models.ml_prediction import MLPrediction


def create_ml_prediction(db: Session, report_id: int, prediction: dict) -> MLPrediction:
    """Persist an ML risk prediction for a review."""
    db_pred = MLPrediction(
        report_id=report_id,
        defect_probability=prediction.get("defect_probability", 0.0),
        maintenance_risk=prediction.get("maintenance_risk", 0.0),
        review_priority=prediction.get("review_priority", "UNKNOWN"),
        human_review_recommended=prediction.get("human_review_recommended", False),
        top_risk_factors=json.dumps(prediction.get("top_risk_factors", [])),
        shap_values=json.dumps(prediction.get("shap_values", {})),
        model_version=prediction.get("model_version", "1.0"),
        model_used=prediction.get("model_used", "heuristic_fallback"),
        disclaimer=prediction.get("disclaimer", ""),
    )
    db.add(db_pred)
    db.flush()
    return db_pred


def get_ml_prediction_for_report(db: Session, report_id: int) -> MLPrediction | None:
    """Return the ML prediction for a given report, or None."""
    return db.query(MLPrediction).filter(MLPrediction.report_id == report_id).first()

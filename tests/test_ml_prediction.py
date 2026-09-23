"""Tests for the ML code risk prediction model."""

import pytest

from app.ml.model import predict_risk, _heuristic_risk


SIMPLE_FEATURES = {
    "loc": 200.0,
    "num_functions": 10.0,
    "num_classes": 2.0,
    "num_imports": 8.0,
    "cyclomatic_complexity_avg": 5.0,
    "max_nesting_depth": 3.0,
    "avg_function_length": 20.0,
    "comment_ratio": 0.15,
    "num_static_findings": 1.0,
    "num_llm_findings": 2.0,
    "severity_weighted_score": 5.0,
    "code_lines": 160.0,
}

HIGH_RISK_FEATURES = {
    "loc": 2000.0,
    "num_functions": 80.0,
    "num_classes": 20.0,
    "num_imports": 50.0,
    "cyclomatic_complexity_avg": 30.0,
    "max_nesting_depth": 8.0,
    "avg_function_length": 80.0,
    "comment_ratio": 0.01,
    "num_static_findings": 20.0,
    "num_llm_findings": 15.0,
    "severity_weighted_score": 80.0,
    "code_lines": 1600.0,
}

LOW_RISK_FEATURES = {
    "loc": 50.0,
    "num_functions": 5.0,
    "num_classes": 1.0,
    "num_imports": 3.0,
    "cyclomatic_complexity_avg": 2.0,
    "max_nesting_depth": 1.0,
    "avg_function_length": 10.0,
    "comment_ratio": 0.30,
    "num_static_findings": 0.0,
    "num_llm_findings": 0.0,
    "severity_weighted_score": 0.0,
    "code_lines": 40.0,
}


class TestPredictRisk:
    """Test the risk prediction output structure and constraints."""

    def test_predict_returns_required_keys(self):
        """predict_risk should return a dict with all required keys."""
        result = predict_risk(SIMPLE_FEATURES)
        required = [
            "defect_probability", "maintenance_risk", "review_priority",
            "human_review_recommended", "top_risk_factors", "shap_values",
            "model_version", "disclaimer",
        ]
        for key in required:
            assert key in result, f"Missing key: {key}"

    def test_probabilities_in_range(self):
        """Defect probability and maintenance risk must be in [0, 1]."""
        result = predict_risk(SIMPLE_FEATURES)
        assert 0.0 <= result["defect_probability"] <= 1.0
        assert 0.0 <= result["maintenance_risk"] <= 1.0

    def test_review_priority_valid_values(self):
        """review_priority must be HIGH, MEDIUM, or LOW."""
        for features in [SIMPLE_FEATURES, HIGH_RISK_FEATURES, LOW_RISK_FEATURES]:
            result = predict_risk(features)
            assert result["review_priority"] in ("HIGH", "MEDIUM", "LOW", "UNKNOWN")

    def test_human_review_is_bool(self):
        """human_review_recommended must be a bool."""
        result = predict_risk(SIMPLE_FEATURES)
        assert isinstance(result["human_review_recommended"], bool)

    def test_top_risk_factors_is_list(self):
        """top_risk_factors must be a list."""
        result = predict_risk(SIMPLE_FEATURES)
        assert isinstance(result["top_risk_factors"], list)

    def test_high_risk_features_higher_probability(self):
        """High-risk code should have higher defect probability than low-risk code."""
        high = predict_risk(HIGH_RISK_FEATURES)
        low = predict_risk(LOW_RISK_FEATURES)
        assert high["defect_probability"] > low["defect_probability"]

    def test_disclaimer_present(self):
        """Disclaimer must be present and non-empty."""
        result = predict_risk(SIMPLE_FEATURES)
        assert isinstance(result["disclaimer"], str)
        assert len(result["disclaimer"]) > 10

    def test_empty_features_does_not_crash(self):
        """Predict should not crash on empty feature dict."""
        result = predict_risk({})
        assert "defect_probability" in result


class TestHeuristicRisk:
    """Test the heuristic fallback risk calculation."""

    def test_high_complexity_increases_risk(self):
        """High cyclomatic complexity should increase heuristic risk."""
        low_cc = {**SIMPLE_FEATURES, "cyclomatic_complexity_avg": 2.0}
        high_cc = {**SIMPLE_FEATURES, "cyclomatic_complexity_avg": 25.0}
        low_p, _ = _heuristic_risk(low_cc)
        high_p, _ = _heuristic_risk(high_cc)
        assert high_p > low_p

    def test_output_in_range(self):
        """Both heuristic outputs must be in [0, 1]."""
        p, m = _heuristic_risk(HIGH_RISK_FEATURES)
        assert 0.0 <= p <= 1.0
        assert 0.0 <= m <= 1.0

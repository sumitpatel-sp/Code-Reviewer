"""Tests for static analysis feature extraction."""

from app.static_analysis.feature_extractor import (
    MODEL_FEATURE_NAMES,
    extract_features,
    features_to_vector,
)


SAMPLE_AGGREGATE = {
    "total_loc": 450,
    "total_functions": 20,
    "total_classes": 5,
    "total_imports": 15,
    "avg_cyclomatic_complexity": 7.5,
    "num_static_findings": 3,
}

SAMPLE_PER_FILE = {
    "app/main.py": {
        "loc": 150,
        "code_lines": 120,
        "comment_lines": 20,
        "comment_ratio": 0.133,
        "max_nesting_depth": 3,
        "avg_function_length": 25.0,
        "cyclomatic_complexity_avg": 6.0,
    },
    "app/utils.py": {
        "loc": 300,
        "code_lines": 240,
        "comment_lines": 30,
        "comment_ratio": 0.1,
        "max_nesting_depth": 4,
        "avg_function_length": 35.0,
        "cyclomatic_complexity_avg": 9.0,
    },
}

SAMPLE_STATIC_FINDINGS = [
    {"severity": "HIGH", "category": "Security"},
    {"severity": "MEDIUM", "category": "Quality"},
]

SAMPLE_LLM_FINDINGS = [
    {"severity": "HIGH", "category": "Bug"},
    {"severity": "LOW", "category": "Documentation"},
    {"severity": "CRITICAL", "category": "Security"},
]


def test_extract_features_returns_all_keys():
    """extract_features should return a dict with all MODEL_FEATURE_NAMES keys."""
    features = extract_features(
        SAMPLE_AGGREGATE, SAMPLE_PER_FILE,
        SAMPLE_STATIC_FINDINGS, SAMPLE_LLM_FINDINGS
    )
    for key in MODEL_FEATURE_NAMES:
        assert key in features, f"Missing feature key: {key}"


def test_extract_features_values_are_numeric():
    """All feature values should be numeric (int or float)."""
    features = extract_features(
        SAMPLE_AGGREGATE, SAMPLE_PER_FILE,
        SAMPLE_STATIC_FINDINGS, SAMPLE_LLM_FINDINGS
    )
    for key, val in features.items():
        assert isinstance(val, (int, float)), f"Feature {key} is not numeric: {val}"


def test_loc_matches_aggregate():
    """LOC feature should match aggregate total_loc."""
    features = extract_features(SAMPLE_AGGREGATE, SAMPLE_PER_FILE, [], [])
    assert features["loc"] == 450.0


def test_severity_weighted_score():
    """Severity-weighted score should weight CRITICAL(4) > HIGH(3) > MEDIUM(2) > LOW(1)."""
    features = extract_features(SAMPLE_AGGREGATE, {}, SAMPLE_STATIC_FINDINGS, SAMPLE_LLM_FINDINGS)
    # CRITICAL=4, HIGH+HIGH=3+3=6, MEDIUM=2, LOW=1  → total = 4+6+2+1 = 13
    assert features["severity_weighted_score"] == 13.0


def test_features_to_vector_correct_order():
    """features_to_vector should return values in MODEL_FEATURE_NAMES order."""
    features = extract_features(SAMPLE_AGGREGATE, SAMPLE_PER_FILE, [], [])
    vector = features_to_vector(features)
    assert len(vector) == len(MODEL_FEATURE_NAMES)
    for i, name in enumerate(MODEL_FEATURE_NAMES):
        assert vector[i] == features[name]


def test_empty_inputs_return_zeros():
    """Empty inputs should not raise and should return all-zero or default features."""
    features = extract_features({}, {}, [], [])
    assert features["loc"] == 0.0
    assert features["severity_weighted_score"] == 0.0
    vector = features_to_vector(features)
    assert all(v == 0.0 for v in vector)


def test_comment_ratio_averaged():
    """Comment ratio should be the average across files."""
    features = extract_features(SAMPLE_AGGREGATE, SAMPLE_PER_FILE, [], [])
    expected = (0.133 + 0.1) / 2
    assert abs(features["comment_ratio"] - expected) < 0.01

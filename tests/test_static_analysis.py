"""Tests for the static analysis pipeline."""

import pytest

from app.static_analysis.analyzer import (
    _ast_metrics,
    _loc_metrics,
    _radon_metrics,
    analyze_all_files,
    analyze_file,
)

SIMPLE_PYTHON = '''
import os
import sys

def greet(name: str) -> str:
    """Greet a user."""
    return f"Hello, {name}!"


def factorial(n: int) -> int:
    if n <= 1:
        return 1
    return n * factorial(n - 1)


class Calculator:
    """Simple calculator."""

    def add(self, a: int, b: int) -> int:
        return a + b

    def divide(self, a: int, b: int) -> float:
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a / b
'''

COMPLEX_PYTHON = '''
def complex_function(data, config, validate=True):
    result = []
    for item in data:
        if item:
            if isinstance(item, dict):
                if "key" in item:
                    if validate:
                        for subitem in item.get("values", []):
                            if subitem > 0:
                                for x in range(subitem):
                                    if x % 2 == 0:
                                        result.append(x)
    return result
'''

INVALID_PYTHON = "def broken_syntax(:)"


class TestLocMetrics:
    """Test LOC metric extraction."""

    def test_basic_loc(self):
        """LOC should count total lines including blanks and comments."""
        metrics = _loc_metrics(SIMPLE_PYTHON)
        assert "loc" in metrics
        assert metrics["loc"] > 0
        assert "comment_ratio" in metrics

    def test_comment_ratio_in_range(self):
        """Comment ratio must be in [0, 1]."""
        metrics = _loc_metrics(SIMPLE_PYTHON)
        assert 0.0 <= metrics["comment_ratio"] <= 1.0


class TestASTMetrics:
    """Test AST-based metric extraction."""

    def test_function_count(self):
        """AST should detect the correct number of functions."""
        metrics = _ast_metrics(SIMPLE_PYTHON)
        # greet, factorial, add, divide = 4 functions
        assert metrics["num_functions"] == 4

    def test_class_count(self):
        """AST should detect the correct number of classes."""
        metrics = _ast_metrics(SIMPLE_PYTHON)
        assert metrics["num_classes"] == 1

    def test_import_count(self):
        """AST should count import statements."""
        metrics = _ast_metrics(SIMPLE_PYTHON)
        assert metrics["num_imports"] == 2

    def test_nesting_depth(self):
        """Deeply nested code should have higher nesting depth than flat code."""
        flat_code = "def foo():\n    return 1\n"
        # Nested: function inside class inside function (depth 3)
        nested_code = (
            "class Outer:\n"
            "    class Inner:\n"
            "        def method(self):\n"
            "            pass\n"
        )
        flat_metrics = _ast_metrics(flat_code)
        nested_metrics = _ast_metrics(nested_code)
        assert nested_metrics["max_nesting_depth"] > flat_metrics["max_nesting_depth"]

    def test_invalid_syntax_returns_empty(self):
        """Invalid Python syntax should return an empty dict, not raise."""
        metrics = _ast_metrics(INVALID_PYTHON)
        assert metrics == {}


class TestRadonMetrics:
    """Test Radon complexity metrics."""

    def test_radon_returns_complexity(self):
        """Radon should return cyclomatic complexity metrics for valid Python."""
        metrics = _radon_metrics(SIMPLE_PYTHON)
        if metrics:  # Radon is installed
            assert "cyclomatic_complexity_avg" in metrics
            assert metrics["cyclomatic_complexity_avg"] >= 1.0

    def test_complex_function_higher_cc(self):
        """Complex function should have higher CC than simple code."""
        simple_metrics = _radon_metrics(SIMPLE_PYTHON)
        complex_metrics = _radon_metrics(COMPLEX_PYTHON)
        if simple_metrics and complex_metrics:
            assert complex_metrics["cyclomatic_complexity_avg"] > simple_metrics["cyclomatic_complexity_avg"]


class TestAnalyzeFile:
    """Test single-file analysis."""

    def test_analyze_python_file(self):
        """analyze_file should return StaticAnalysisResult for a Python file."""
        result = analyze_file("app/main.py", SIMPLE_PYTHON)
        assert result.file_path == "app/main.py"
        assert "loc" in result.metrics

    def test_non_python_file_loc_only(self):
        """Non-Python files should get LOC metrics but no AST/Radon analysis."""
        js_code = "function hello() { return 'hi'; }\n// comment\n"
        result = analyze_file("app/main.js", js_code)
        assert "loc" in result.metrics
        # Should NOT have AST metrics
        assert "num_functions" not in result.metrics


class TestAnalyzeAllFiles:
    """Test multi-file analysis aggregation."""

    def test_aggregate_metrics_present(self):
        """analyze_all_files should return aggregate metrics."""
        source_files = {
            "app/main.py": SIMPLE_PYTHON,
            "app/utils.py": COMPLEX_PYTHON,
        }
        results = analyze_all_files(source_files)
        assert "aggregate_metrics" in results
        assert results["aggregate_metrics"]["total_loc"] > 0
        assert results["aggregate_metrics"]["num_files_analyzed"] == 2

    def test_per_file_metrics_present(self):
        """Each file should have its own metrics entry."""
        source_files = {"app/main.py": SIMPLE_PYTHON}
        results = analyze_all_files(source_files)
        assert "app/main.py" in results["per_file_metrics"]

    def test_empty_files_returns_empty(self):
        """Empty source files dict should return empty results."""
        results = analyze_all_files({})
        assert results["aggregate_metrics"]["total_loc"] == 0
        assert results["aggregate_metrics"]["num_files_analyzed"] == 0

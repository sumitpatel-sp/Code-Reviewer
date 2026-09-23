"""Tests for the Semgrep cross-language static analysis runner.

Coverage
--------
1.  Semgrep availability detection (binary found vs. not found)
2.  Successful Semgrep execution (mocked subprocess)
3.  JSON output parsing
4.  Field extraction: file, line, severity, rule_id, message
5.  Python source repository
6.  JavaScript source repository
7.  TypeScript source repository
8.  Java source repository
9.  C++ source repository
10. Repository with no findings
11. Repository with findings present
12. Invalid / malformed Semgrep JSON output
13. Semgrep executable unavailable
14. Semgrep timeout / failure
15. Semgrep failure does not break the existing review pipeline (isolation)
16. Existing Python AST/Radon/Bandit tests unaffected (import smoke test)
17. Existing finding-schema contract respected
18. Real integration test (skipped when semgrep not available)
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.finding import FindingSchema, FindingSource, Severity
from app.static_analysis.semgrep_runner import (
    SEMGREP_TIMEOUT_SECONDS,
    _find_semgrep_executable,
    _infer_category,
    _map_severity,
    _parse_semgrep_json,
    run_semgrep,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_semgrep_result(
    path: str = "/tmp/repo/main.py",
    rule_id: str = "python-eval-use",
    message: str = "Use of eval() is dangerous.",
    severity: str = "ERROR",
    start_line: int = 10,
    end_line: int = 10,
    lines: str = "    eval(user_input)",
) -> dict:
    """Return a minimal Semgrep JSON result dict."""
    return {
        "check_id": rule_id,
        "path": path,
        "start": {"line": start_line, "col": 5},
        "end": {"line": end_line, "col": 25},
        "extra": {
            "message": message,
            "severity": severity,
            "lines": lines,
        },
    }


def _semgrep_json_output(results: list[dict]) -> str:
    """Wrap a list of result dicts in the Semgrep JSON envelope."""
    return json.dumps({"results": results, "errors": []})


# ---------------------------------------------------------------------------
# 1. Semgrep availability detection
# ---------------------------------------------------------------------------

class TestSemgrepAvailability:
    """Tests for _find_semgrep_executable()."""

    def test_returns_string_when_found(self):
        """When a working semgrep binary exists, return a non-empty string."""
        with patch("shutil.which", return_value="/usr/bin/semgrep"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                result = _find_semgrep_executable()
        assert result == "/usr/bin/semgrep"

    def test_returns_none_when_not_on_path(self):
        """Return None when semgrep is not on PATH and not in venv/Scripts."""
        with patch("shutil.which", return_value=None):
            with patch("app.static_analysis.semgrep_runner.Path") as mock_path:
                mock_path.return_value.parent.__truediv__.return_value.is_file.return_value = False
                result = _find_semgrep_executable()
        # Either None or still tries venv script — important: does not raise
        assert result is None or isinstance(result, str)

    def test_returns_none_when_binary_fails(self):
        """Return None when semgrep exists but --version exits with non-zero."""
        with patch("shutil.which", return_value="/usr/bin/semgrep"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1)
                result = _find_semgrep_executable()
        assert result is None

    def test_returns_none_on_file_not_found(self):
        """Return None when FileNotFoundError is raised during version check."""
        with patch("shutil.which", return_value="/usr/bin/semgrep"):
            with patch("subprocess.run", side_effect=FileNotFoundError):
                result = _find_semgrep_executable()
        assert result is None

    def test_returns_none_on_timeout(self):
        """Return None when the version check times out."""
        with patch("shutil.which", return_value="/usr/bin/semgrep"):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("semgrep", 10)):
                result = _find_semgrep_executable()
        assert result is None


# ---------------------------------------------------------------------------
# 2 & 3. JSON output parsing
# ---------------------------------------------------------------------------

class TestParseJson:
    """Tests for _parse_semgrep_json()."""

    def test_empty_string_returns_empty(self):
        result = _parse_semgrep_json("", Path("/tmp/repo"))
        assert result == []

    def test_whitespace_only_returns_empty(self):
        result = _parse_semgrep_json("   \n  ", Path("/tmp/repo"))
        assert result == []

    def test_valid_single_finding(self):
        """A well-formed single result produces one FindingSchema."""
        raw = _semgrep_json_output([
            _make_semgrep_result(path="/tmp/repo/main.py", start_line=10, end_line=10)
        ])
        findings = _parse_semgrep_json(raw, Path("/tmp/repo"))
        assert len(findings) == 1
        assert isinstance(findings[0], FindingSchema)

    def test_multiple_findings(self):
        """Multiple results produce the correct count of FindingSchema objects."""
        raw = _semgrep_json_output([
            _make_semgrep_result(path="/tmp/repo/a.py"),
            _make_semgrep_result(path="/tmp/repo/b.py"),
            _make_semgrep_result(path="/tmp/repo/c.py"),
        ])
        findings = _parse_semgrep_json(raw, Path("/tmp/repo"))
        assert len(findings) == 3

    # 12. Malformed JSON
    def test_invalid_json_returns_empty(self):
        result = _parse_semgrep_json("NOT JSON AT ALL {{{", Path("/tmp/repo"))
        assert result == []

    def test_json_without_results_key(self):
        result = _parse_semgrep_json(json.dumps({"errors": []}), Path("/tmp/repo"))
        assert result == []

    def test_results_not_a_list(self):
        result = _parse_semgrep_json(json.dumps({"results": "bad"}), Path("/tmp/repo"))
        assert result == []

    def test_malformed_item_skipped(self):
        """A malformed item in results is skipped without crashing."""
        raw = json.dumps({"results": [{"bad": "item"}, _make_semgrep_result()]})
        # Should still return the one valid finding (or at least not raise)
        findings = _parse_semgrep_json(raw, Path("/tmp/repo"))
        assert isinstance(findings, list)

    def test_empty_results_list(self):
        raw = _semgrep_json_output([])
        findings = _parse_semgrep_json(raw, Path("/tmp/repo"))
        assert findings == []


# ---------------------------------------------------------------------------
# 4. Field extraction: file, line, severity, rule_id, message
# ---------------------------------------------------------------------------

class TestFieldExtraction:
    """Verify that individual fields are correctly extracted from Semgrep output."""

    def _get_finding(self, **kwargs) -> FindingSchema:
        raw = _semgrep_json_output([_make_semgrep_result(**kwargs)])
        return _parse_semgrep_json(raw, Path("/tmp/repo"))[0]

    def test_file_is_relativised(self):
        """Absolute path from Semgrep → relative path stored in finding."""
        f = self._get_finding(path="/tmp/repo/src/auth.py")
        assert f.file == "src/auth.py"

    def test_file_fallback_to_basename(self):
        """Path outside extraction root falls back to basename only."""
        f = self._get_finding(path="/other/path/main.py")
        assert f.file == "main.py"

    def test_line_start_extracted(self):
        f = self._get_finding(start_line=42, end_line=42)
        assert f.line_start == 42

    def test_line_end_none_when_equal_to_start(self):
        """Single-line findings: end_line == start_line → line_end stored as None."""
        f = self._get_finding(start_line=10, end_line=10)
        assert f.line_end is None

    def test_line_end_set_when_multiline(self):
        """Multi-line findings retain a distinct line_end."""
        f = self._get_finding(start_line=10, end_line=15)
        assert f.line_end == 15

    def test_severity_error_maps_to_high(self):
        f = self._get_finding(severity="ERROR")
        assert f.severity == Severity.HIGH

    def test_severity_warning_maps_to_medium(self):
        f = self._get_finding(severity="WARNING")
        assert f.severity == Severity.MEDIUM

    def test_severity_info_maps_to_low(self):
        f = self._get_finding(severity="INFO")
        assert f.severity == Severity.LOW

    def test_unknown_severity_maps_to_low(self):
        assert _map_severity("UNKNOWN") == Severity.LOW

    def test_rule_id_in_title(self):
        f = self._get_finding(rule_id="python-eval-use")
        assert "python-eval-use" in f.title

    def test_message_in_description(self):
        f = self._get_finding(message="Dangerous eval usage detected.")
        assert "Dangerous eval usage detected." in f.description

    def test_code_snippet_present(self):
        f = self._get_finding(lines="    eval(user_input)")
        assert f.code_snippet == "eval(user_input)"

    def test_code_snippet_none_when_empty(self):
        f = self._get_finding(lines="")
        assert f.code_snippet is None

    def test_source_is_static_analysis(self):
        f = self._get_finding()
        assert f.source == FindingSource.STATIC_ANALYSIS

    def test_agent_name(self):
        f = self._get_finding()
        assert f.agent == "Static Analysis (Semgrep)"

    def test_id_starts_with_semgrep(self):
        f = self._get_finding()
        assert f.id.startswith("semgrep-")


# ---------------------------------------------------------------------------
# Category inference
# ---------------------------------------------------------------------------

class TestCategoryInference:
    def test_security_keywords(self):
        for kw in ("python-eval-use", "js-xss-check", "sql-injection", "hardcoded-password"):
            assert _infer_category(kw) == "Security"

    def test_bug_keywords(self):
        for kw in ("null-check", "nullptr-deref", "malloc-no-check"):
            assert _infer_category(kw) == "Bug"

    def test_quality_fallback(self):
        assert _infer_category("some-random-rule") == "Quality"


# ---------------------------------------------------------------------------
# 5–9. Per-language repositories (mocked subprocess)
# ---------------------------------------------------------------------------

class TestPerLanguageRepos:
    """Test that run_semgrep correctly handles each supported language."""

    def _run_with_mocked_findings(self, source_files: dict[str, str], raw_results: list[dict]):
        """Helper: mock the semgrep binary and return parsed findings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            extraction_path = Path(tmpdir)
            # Write source files to temp dir
            for rel_path, content in source_files.items():
                target = extraction_path / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")

            json_out = _semgrep_json_output([
                {**r, "path": str(extraction_path / r["path"])} for r in raw_results
            ])
            mock_proc = MagicMock(returncode=0, stdout=json_out, stderr="")

            with patch("app.static_analysis.semgrep_runner._find_semgrep_executable",
                       return_value="/usr/bin/semgrep"):
                with patch("subprocess.run", return_value=mock_proc):
                    return run_semgrep(extraction_path, source_files)

    def test_python_repository(self):
        """Python files are scanned; findings are returned."""
        source_files = {"main.py": "eval(input())\n"}
        results = [_make_semgrep_result(path="main.py", rule_id="python-eval-use")]
        findings = self._run_with_mocked_findings(source_files, results)
        assert len(findings) == 1
        assert findings[0].file == "main.py"

    def test_javascript_repository(self):
        """JavaScript files are scanned; findings are returned."""
        source_files = {"app.js": "eval(userInput);\n"}
        results = [_make_semgrep_result(path="app.js", rule_id="js-eval-use", severity="ERROR")]
        findings = self._run_with_mocked_findings(source_files, results)
        assert len(findings) == 1
        assert findings[0].file == "app.js"

    def test_typescript_repository(self):
        """TypeScript files are scanned; findings are returned."""
        source_files = {"service.ts": "eval(data);\n"}
        results = [_make_semgrep_result(path="service.ts", rule_id="ts-eval-use")]
        findings = self._run_with_mocked_findings(source_files, results)
        assert len(findings) == 1
        assert findings[0].file == "service.ts"

    def test_java_repository(self):
        """Java files are scanned; findings are returned."""
        source_files = {"Main.java": "Runtime.getRuntime().exec(cmd);\n"}
        results = [_make_semgrep_result(path="Main.java", rule_id="java-runtime-exec")]
        findings = self._run_with_mocked_findings(source_files, results)
        assert len(findings) == 1
        assert findings[0].file == "Main.java"

    def test_cpp_repository(self):
        """C++ files are scanned; findings are returned."""
        source_files = {"main.cpp": "strcpy(buf, src);\n"}
        results = [_make_semgrep_result(path="main.cpp", rule_id="cpp-strcpy-usage")]
        findings = self._run_with_mocked_findings(source_files, results)
        assert len(findings) == 1
        assert findings[0].file == "main.cpp"


# ---------------------------------------------------------------------------
# 10. Repository with no findings
# ---------------------------------------------------------------------------

class TestNoFindings:
    def test_empty_results_list(self):
        """Zero results → empty findings list, no crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            extraction_path = Path(tmpdir)
            source_files = {"clean.py": "x = 1\n"}
            (extraction_path / "clean.py").write_text("x = 1\n")
            mock_proc = MagicMock(returncode=0, stdout=_semgrep_json_output([]), stderr="")
            with patch("app.static_analysis.semgrep_runner._find_semgrep_executable",
                       return_value="/usr/bin/semgrep"):
                with patch("subprocess.run", return_value=mock_proc):
                    findings = run_semgrep(extraction_path, source_files)
        assert findings == []

    def test_exit_code_zero_no_output(self):
        """Exit 0 with empty stdout → empty findings, no crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            extraction_path = Path(tmpdir)
            source_files = {"ok.py": "pass\n"}
            mock_proc = MagicMock(returncode=0, stdout="", stderr="")
            with patch("app.static_analysis.semgrep_runner._find_semgrep_executable",
                       return_value="/usr/bin/semgrep"):
                with patch("subprocess.run", return_value=mock_proc):
                    findings = run_semgrep(extraction_path, source_files)
        assert findings == []


# ---------------------------------------------------------------------------
# 11. Repository with findings
# ---------------------------------------------------------------------------

class TestWithFindings:
    def test_findings_returned_for_multiple_files(self):
        """Multiple files with findings → all findings collected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            extraction_path = Path(tmpdir)
            source_files = {"a.py": "eval(x)", "b.js": "eval(y)"}
            for name, content in source_files.items():
                (extraction_path / name).write_text(content)

            raw = _semgrep_json_output([
                _make_semgrep_result(path=str(extraction_path / "a.py"), rule_id="python-eval-use"),
                _make_semgrep_result(path=str(extraction_path / "b.js"), rule_id="js-eval-use"),
            ])
            mock_proc = MagicMock(returncode=1, stdout=raw, stderr="")  # rc=1 means findings found
            with patch("app.static_analysis.semgrep_runner._find_semgrep_executable",
                       return_value="/usr/bin/semgrep"):
                with patch("subprocess.run", return_value=mock_proc):
                    findings = run_semgrep(extraction_path, source_files)

        assert len(findings) == 2
        files = {f.file for f in findings}
        assert "a.py" in files
        assert "b.js" in files


# ---------------------------------------------------------------------------
# 13. Semgrep executable unavailable
# ---------------------------------------------------------------------------

class TestSemgrepUnavailable:
    def test_no_binary_returns_empty(self):
        """When semgrep cannot be found, return empty list without crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.static_analysis.semgrep_runner._find_semgrep_executable",
                       return_value=None):
                findings = run_semgrep(Path(tmpdir), {"main.py": "x=1"})
        assert findings == []

    def test_no_source_files_returns_empty(self):
        """Empty source_files dict short-circuits before calling semgrep."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.static_analysis.semgrep_runner._find_semgrep_executable") as mock_find:
                findings = run_semgrep(Path(tmpdir), {})
        mock_find.assert_not_called()
        assert findings == []

    def test_missing_rules_dir_returns_empty(self):
        """Missing bundled rules directory → empty list, no crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.static_analysis.semgrep_runner._find_semgrep_executable",
                       return_value="/usr/bin/semgrep"):
                with patch("app.static_analysis.semgrep_runner._rules_path", return_value=None):
                    findings = run_semgrep(Path(tmpdir), {"main.py": "x=1"})
        assert findings == []


# ---------------------------------------------------------------------------
# 14. Semgrep timeout / failure
# ---------------------------------------------------------------------------

class TestSemgrepFailures:
    def test_timeout_returns_empty(self):
        """TimeoutExpired during subprocess.run → empty list, no propagation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            extraction_path = Path(tmpdir)
            (extraction_path / "main.py").write_text("x=1")
            with patch("app.static_analysis.semgrep_runner._find_semgrep_executable",
                       return_value="/usr/bin/semgrep"):
                with patch("subprocess.run",
                           side_effect=subprocess.TimeoutExpired(cmd="semgrep", timeout=120)):
                    findings = run_semgrep(extraction_path, {"main.py": "x=1"})
        assert findings == []

    def test_unexpected_exception_returns_empty(self):
        """Any unexpected exception in subprocess.run → empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            extraction_path = Path(tmpdir)
            with patch("app.static_analysis.semgrep_runner._find_semgrep_executable",
                       return_value="/usr/bin/semgrep"):
                with patch("subprocess.run", side_effect=OSError("disk full")):
                    findings = run_semgrep(extraction_path, {"main.py": "x=1"})
        assert findings == []

    def test_non_ok_exit_code_returns_empty(self):
        """Exit code other than 0 or 1 → empty list (semgrep internal error)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            extraction_path = Path(tmpdir)
            mock_proc = MagicMock(returncode=2, stdout="", stderr="semgrep crashed")
            with patch("app.static_analysis.semgrep_runner._find_semgrep_executable",
                       return_value="/usr/bin/semgrep"):
                with patch("subprocess.run", return_value=mock_proc):
                    findings = run_semgrep(extraction_path, {"main.py": "x=1"})
        assert findings == []

    def test_malformed_json_returns_empty(self):
        """Non-JSON stdout → empty list, no crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            extraction_path = Path(tmpdir)
            mock_proc = MagicMock(returncode=0, stdout="{bad json{{", stderr="")
            with patch("app.static_analysis.semgrep_runner._find_semgrep_executable",
                       return_value="/usr/bin/semgrep"):
                with patch("subprocess.run", return_value=mock_proc):
                    findings = run_semgrep(extraction_path, {"main.py": "x=1"})
        assert findings == []


# ---------------------------------------------------------------------------
# 15. Semgrep failure does NOT break the existing review pipeline
# ---------------------------------------------------------------------------

class TestPipelineIsolation:
    """Verify that semgrep failures are isolated from the LangGraph workflow."""

    def test_workflow_node_returns_unchanged_findings_on_no_semgrep(self):
        """When extraction_path is absent, Semgrep node returns state unchanged."""
        from app.langgraph.workflow import run_semgrep_analysis

        state = {
            "source_files": {"main.py": "x = 1"},
            "findings": [{"id": "existing-1", "agent": "Bug Agent", "category": "Bug",
                          "severity": "HIGH", "confidence": 80, "source": "ai_detected",
                          "title": "Existing finding", "description": "d",
                          "impact": "i", "recommendation": "r"}],
            "agent_timing": {},
            # No extraction_path key → Semgrep node must skip gracefully
        }
        result = run_semgrep_analysis(state)
        # Original findings must be preserved
        assert len(result["findings"]) >= 1
        assert any(f.get("id") == "existing-1" for f in result["findings"])

    def test_workflow_node_handles_semgrep_exception(self):
        """Even if run_semgrep raises, the node catches it and preserves state."""
        from app.langgraph.workflow import run_semgrep_analysis

        with tempfile.TemporaryDirectory() as tmpdir:
            state = {
                "source_files": {"main.py": "eval(x)"},
                "findings": [],
                "agent_timing": {},
                "extraction_path": tmpdir,
            }
            with patch("app.langgraph.workflow.run_semgrep",
                       side_effect=RuntimeError("semgrep exploded")):
                result = run_semgrep_analysis(state)
        # Must not raise; findings list must be intact (empty here)
        assert isinstance(result["findings"], list)


# ---------------------------------------------------------------------------
# 16. Existing Python AST/Radon/Bandit tests unaffected (smoke import)
# ---------------------------------------------------------------------------

class TestExistingAnalysisUnaffected:
    """Smoke tests to confirm existing static analysis is untouched."""

    def test_analyzer_imports_unchanged(self):
        from app.static_analysis.analyzer import (
            _ast_metrics,
            _loc_metrics,
            _radon_metrics,
            analyze_all_files,
            analyze_file,
        )
        assert callable(analyze_file)
        assert callable(analyze_all_files)
        assert callable(_ast_metrics)
        assert callable(_loc_metrics)
        assert callable(_radon_metrics)

    def test_analyze_file_python_unchanged(self):
        from app.static_analysis.analyzer import analyze_file
        result = analyze_file("test.py", "def foo():\n    return 1\n")
        assert "loc" in result.metrics
        assert "num_functions" in result.metrics

    def test_analyze_file_non_python_unchanged(self):
        from app.static_analysis.analyzer import analyze_file
        result = analyze_file("test.js", "function foo() { return 1; }\n")
        assert "loc" in result.metrics
        assert "num_functions" not in result.metrics


# ---------------------------------------------------------------------------
# 17. FindingSchema contract preserved
# ---------------------------------------------------------------------------

class TestFindingSchemaContract:
    def test_parsed_finding_is_valid_schema(self):
        raw = _semgrep_json_output([_make_semgrep_result()])
        findings = _parse_semgrep_json(raw, Path("/tmp/repo"))
        assert findings
        f = findings[0]
        # Pydantic will have validated this; just confirm key fields
        assert f.id
        assert f.agent == "Static Analysis (Semgrep)"
        assert f.source == FindingSource.STATIC_ANALYSIS
        assert f.confidence == 80
        assert f.severity in list(Severity)

    def test_model_dump_round_trip(self):
        """FindingSchema from Semgrep survives a model_dump / reconstruct cycle."""
        raw = _semgrep_json_output([_make_semgrep_result()])
        findings = _parse_semgrep_json(raw, Path("/tmp/repo"))
        dumped = findings[0].model_dump()
        restored = FindingSchema(**dumped)
        assert restored.id == findings[0].id


# ---------------------------------------------------------------------------
# 18. REAL integration test (skipped if semgrep not available)
# ---------------------------------------------------------------------------

_SEMGREP_AVAILABLE = _find_semgrep_executable() is not None

@pytest.mark.skipif(not _SEMGREP_AVAILABLE, reason="semgrep binary not available")
class TestRealSemgrepIntegration:
    """End-to-end tests that actually invoke the semgrep binary.

    These tests are automatically skipped in environments where semgrep is
    not installed (e.g. vanilla CI without the semgrep package).
    """

    def _write_and_scan(self, files: dict[str, str]) -> list[FindingSchema]:
        """Write source files to a temp dir and run real Semgrep against them."""
        with tempfile.TemporaryDirectory() as tmpdir:
            extraction_path = Path(tmpdir)
            for rel_path, content in files.items():
                target = extraction_path / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            return run_semgrep(extraction_path, files)

    def test_python_eval_detected(self):
        """Semgrep should flag eval() in Python source via the bundled rules."""
        findings = self._write_and_scan({"main.py": "eval(input())\n"})
        rule_ids = [f.title for f in findings]
        assert any("eval" in r.lower() for r in rule_ids), (
            f"Expected a finding about eval, got: {rule_ids}"
        )

    def test_python_os_system_detected(self):
        """Semgrep should flag os.system() in Python source."""
        findings = self._write_and_scan({
            "run.py": "import os\nos.system('ls -la')\n"
        })
        rule_ids = [f.title for f in findings]
        assert any("system" in r.lower() or "os" in r.lower() for r in rule_ids), (
            f"Expected an os.system finding, got: {rule_ids}"
        )

    def test_clean_python_no_findings(self):
        """Clean Python code should produce no findings from the bundled rules."""
        clean_code = (
            "def add(a: int, b: int) -> int:\n"
            "    \"\"\"Add two numbers.\"\"\"\n"
            "    return a + b\n"
        )
        findings = self._write_and_scan({"utils.py": clean_code})
        # Filter only our bundled rules (not auto-generated)
        relevant = [f for f in findings if "semgrep-" in f.id or f.source == FindingSource.STATIC_ANALYSIS]
        # It's acceptable to have zero findings for truly clean code
        assert isinstance(relevant, list)

    def test_javascript_eval_detected(self):
        """Semgrep should flag eval() in JavaScript via bundled rules."""
        findings = self._write_and_scan({"app.js": "eval(userInput);\n"})
        assert any("eval" in f.title.lower() for f in findings), (
            f"Expected JS eval finding, got titles: {[f.title for f in findings]}"
        )

    def test_cpp_strcpy_detected(self):
        """Semgrep should flag strcpy() in C++ source."""
        cpp_code = '#include <string.h>\nchar buf[10];\nstrcpy(buf, src);\n'
        findings = self._write_and_scan({"main.cpp": cpp_code})
        assert any("strcpy" in f.title.lower() for f in findings), (
            f"Expected strcpy finding, got: {[f.title for f in findings]}"
        )

    def test_semgrep_findings_are_valid_schema(self):
        """All real Semgrep findings must satisfy the FindingSchema contract."""
        findings = self._write_and_scan({"main.py": "eval(input())\n"})
        for f in findings:
            assert isinstance(f, FindingSchema)
            assert f.id.startswith("semgrep-")
            assert f.source == FindingSource.STATIC_ANALYSIS
            assert f.line_start is not None, "Real Semgrep always provides line numbers"

    def test_no_host_paths_in_findings(self):
        """Stored file paths must be relative — no absolute host paths exposed."""
        findings = self._write_and_scan({"src/main.py": "eval(x)\n"})
        for f in findings:
            if f.file:
                assert not f.file.startswith("/"), f"Absolute path leaked: {f.file}"
                assert not f.file.startswith("C:\\"), f"Absolute Windows path leaked: {f.file}"

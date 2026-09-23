"""Deterministic static analysis for uploaded Python source files.

Provides three layers of analysis:
1. Python AST — structural metrics (functions, classes, imports, nesting)
2. Radon — cyclomatic complexity and maintainability index
3. Bandit — security issue scanning

Non-Python files receive only basic LOC metrics (no AST/Radon/Bandit).
All findings are tagged source='static_analysis' to distinguish them from
AI-detected findings.
"""

from __future__ import annotations

import ast
import logging
import uuid
from pathlib import Path

from app.schemas.finding import FindingSchema, FindingSource, Severity

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
#  AST helpers                                                                 #
# --------------------------------------------------------------------------- #

class _MaxNestingVisitor(ast.NodeVisitor):
    """Walk an AST tree and record the maximum function/class nesting depth."""

    def __init__(self) -> None:
        self._depth = 0
        self.max_depth = 0

    def _visit_nested(self, node: ast.AST) -> None:
        self._depth += 1
        self.max_depth = max(self.max_depth, self._depth)
        self.generic_visit(node)
        self._depth -= 1

    visit_FunctionDef = _visit_nested       # type: ignore[assignment]
    visit_AsyncFunctionDef = _visit_nested  # type: ignore[assignment]
    visit_ClassDef = _visit_nested          # type: ignore[assignment]


def _ast_metrics(source: str) -> dict:
    """Parse Python source and extract structural metrics via the AST."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}

    functions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    classes   = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    imports   = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]

    nesting_visitor = _MaxNestingVisitor()
    nesting_visitor.visit(tree)

    # Average function body length (in lines)
    func_lengths = []
    for func in functions:
        if hasattr(func, "end_lineno") and hasattr(func, "lineno"):
            func_lengths.append(func.end_lineno - func.lineno)

    return {
        "num_functions": len(functions),
        "num_classes": len(classes),
        "num_imports": len(imports),
        "max_nesting_depth": nesting_visitor.max_depth,
        "avg_function_length": (sum(func_lengths) / len(func_lengths)) if func_lengths else 0.0,
    }


def _loc_metrics(source: str) -> dict:
    """Compute basic line-of-code metrics that work for any language."""
    lines = source.splitlines()
    total = len(lines)
    blank = sum(1 for l in lines if not l.strip())
    comment = sum(
        1 for l in lines
        if l.strip().startswith(("#", "//", "/*", "*", "'''", '"""'))
    )
    code = total - blank - comment
    comment_ratio = comment / total if total else 0.0
    return {
        "loc": total,
        "code_lines": code,
        "blank_lines": blank,
        "comment_lines": comment,
        "comment_ratio": round(comment_ratio, 3),
    }


# --------------------------------------------------------------------------- #
#  Radon integration                                                           #
# --------------------------------------------------------------------------- #

def _radon_metrics(source: str) -> dict:
    """Compute cyclomatic complexity and maintainability index using Radon.

    Returns an empty dict if Radon is not installed or analysis fails.
    """
    try:
        from radon.complexity import cc_visit
        from radon.metrics import mi_visit
    except ImportError:
        logger.debug("Radon not installed — skipping complexity analysis.")
        return {}

    try:
        blocks = cc_visit(source)
        complexities = [b.complexity for b in blocks]
        avg_cc = sum(complexities) / len(complexities) if complexities else 0.0
        max_cc = max(complexities, default=0)

        mi_score = mi_visit(source, multi=True)

        return {
            "cyclomatic_complexity_avg": round(avg_cc, 2),
            "cyclomatic_complexity_max": max_cc,
            "maintainability_index": round(mi_score, 2),
            "num_complex_functions": sum(1 for c in complexities if c > 10),
        }
    except Exception as exc:
        logger.debug("Radon analysis failed: %s", exc)
        return {}


# --------------------------------------------------------------------------- #
#  Bandit integration                                                          #
# --------------------------------------------------------------------------- #

_BANDIT_SEVERITY_MAP = {
    "HIGH": Severity.HIGH,
    "MEDIUM": Severity.MEDIUM,
    "LOW": Severity.LOW,
}


def _bandit_findings(source: str, file_path: str) -> list[FindingSchema]:
    """Run Bandit on Python source and return structured findings.

    Returns an empty list if Bandit is not installed or analysis fails.
    """
    try:
        import bandit.core.manager as bandit_manager
        import bandit.core.config as bandit_config
        import bandit.core.issue as bandit_issue
        from bandit.core import node_visitor
        import tempfile, os
    except ImportError:
        logger.debug("Bandit not installed — skipping security static analysis.")
        return []

    findings: list[FindingSchema] = []
    tmp_path: str | None = None
    try:
        # Write source to a temp file so Bandit can parse it
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(source)
            tmp_path = tmp.name

        conf = bandit_config.BanditConfig()
        mgr = bandit_manager.BanditManager(conf, "file", False)
        mgr.discover_files([tmp_path])
        mgr.run_tests()

        for issue in mgr.get_issue_list():
            severity = _BANDIT_SEVERITY_MAP.get(issue.severity.name, Severity.MEDIUM)
            confidence_map = {"HIGH": 85, "MEDIUM": 65, "LOW": 45}
            confidence = confidence_map.get(issue.confidence.name, 60)

            findings.append(
                FindingSchema(
                    id=f"bandit-{uuid.uuid4().hex[:8]}",
                    agent="Static Analysis (Bandit)",
                    category="Security",
                    severity=severity,
                    confidence=confidence,
                    source=FindingSource.STATIC_ANALYSIS,
                    file=file_path,
                    line_start=issue.lineno if issue.lineno else None,
                    line_end=issue.lineno if issue.lineno else None,
                    title=issue.test,
                    description=issue.text,
                    impact=f"Bandit test ID: {issue.test_id}. CWE: {getattr(issue, 'cwe', 'Unknown')}",
                    recommendation="Review and remediate this security issue.",
                    code_snippet=issue.get_code().strip() if hasattr(issue, "get_code") else None,
                    suggested_fix=None,
                )
            )
    except Exception as exc:
        logger.debug("Bandit analysis failed for %s: %s", file_path, exc)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    return findings


# --------------------------------------------------------------------------- #
#  High-complexity function findings                                           #
# --------------------------------------------------------------------------- #

def _complexity_findings(source: str, file_path: str) -> list[FindingSchema]:
    """Generate findings for functions with high cyclomatic complexity."""
    try:
        from radon.complexity import cc_visit
    except ImportError:
        return []

    findings: list[FindingSchema] = []
    try:
        for block in cc_visit(source):
            if block.complexity >= 15:
                severity = Severity.HIGH if block.complexity >= 25 else Severity.MEDIUM
                findings.append(
                    FindingSchema(
                        id=f"complexity-{uuid.uuid4().hex[:8]}",
                        agent="Static Analysis (Radon)",
                        category="Quality",
                        severity=severity,
                        confidence=95,
                        source=FindingSource.STATIC_ANALYSIS,
                        file=file_path,
                        line_start=block.lineno,
                        line_end=None,
                        title=f"High cyclomatic complexity in '{block.name}' (CC={block.complexity})",
                        description=(
                            f"Function '{block.name}' has a cyclomatic complexity of {block.complexity}. "
                            "Values above 10 indicate complex, hard-to-test code. "
                            "Values above 25 are considered very high risk."
                        ),
                        impact="Hard to test, maintain, and understand. Increases defect probability.",
                        recommendation=(
                            "Break this function into smaller, focused functions. "
                            "Aim for cyclomatic complexity below 10."
                        ),
                        code_snippet=None,
                        suggested_fix=None,
                    )
                )
    except Exception as exc:
        logger.debug("Complexity analysis failed for %s: %s", file_path, exc)
    return findings


# --------------------------------------------------------------------------- #
#  Public interface                                                            #
# --------------------------------------------------------------------------- #

class StaticAnalysisResult:
    """Container for one file's complete static analysis output."""

    def __init__(
        self,
        file_path: str,
        metrics: dict,
        findings: list[FindingSchema],
    ) -> None:
        self.file_path = file_path
        self.metrics = metrics
        self.findings = findings


def analyze_file(file_path: str, source: str) -> StaticAnalysisResult:
    """Run all applicable static analyses on a single source file."""
    metrics: dict = {}
    findings: list[FindingSchema] = []

    # LOC metrics apply to all languages
    metrics.update(_loc_metrics(source))

    # Python-specific analysis
    if file_path.endswith(".py"):
        metrics.update(_ast_metrics(source))
        metrics.update(_radon_metrics(source))
        findings.extend(_bandit_findings(source, file_path))
        findings.extend(_complexity_findings(source, file_path))

    return StaticAnalysisResult(file_path=file_path, metrics=metrics, findings=findings)


def analyze_all_files(source_files: dict[str, str]) -> dict:
    """Run static analysis across all source files and return aggregated results.

    Returns a dict with:
      - 'findings': list of all static-analysis FindingSchema dicts
      - 'per_file_metrics': dict[filename -> metrics dict]
      - 'aggregate_metrics': combined metrics across all files
    """
    all_findings: list[FindingSchema] = []
    per_file_metrics: dict[str, dict] = {}

    for file_path, source in source_files.items():
        try:
            result = analyze_file(file_path, source)
            per_file_metrics[file_path] = result.metrics
            all_findings.extend(result.findings)
        except Exception as exc:
            logger.warning("Static analysis failed for %s: %s", file_path, exc)

    # Aggregate metrics
    total_loc = sum(m.get("loc", 0) for m in per_file_metrics.values())
    total_functions = sum(m.get("num_functions", 0) for m in per_file_metrics.values())
    total_classes = sum(m.get("num_classes", 0) for m in per_file_metrics.values())
    total_imports = sum(m.get("num_imports", 0) for m in per_file_metrics.values())
    cc_values = [m["cyclomatic_complexity_avg"] for m in per_file_metrics.values() if "cyclomatic_complexity_avg" in m]
    avg_cc = sum(cc_values) / len(cc_values) if cc_values else 0.0

    aggregate = {
        "total_loc": total_loc,
        "total_functions": total_functions,
        "total_classes": total_classes,
        "total_imports": total_imports,
        "avg_cyclomatic_complexity": round(avg_cc, 2),
        "num_static_findings": len(all_findings),
        "num_files_analyzed": len(per_file_metrics),
    }

    logger.info(
        "Static analysis complete: %d files, %d findings, %d total LOC.",
        len(per_file_metrics), len(all_findings), total_loc,
    )

    return {
        "findings": [f.model_dump() for f in all_findings],
        "per_file_metrics": per_file_metrics,
        "aggregate_metrics": aggregate,
    }

"""Semgrep-based cross-language static analysis runner.

Executes the Semgrep CLI as a subprocess against the extracted repository
directory, using version-controlled YAML rule files bundled under
``semgrep_rules/`` at the project root.  Supports Python, JavaScript,
TypeScript, Java, and C++.

Design constraints
------------------
* **Never raises** — every error path returns an empty list so the rest of
  the LangGraph review pipeline is completely unaffected.
* **No network access** — the bundled rule files are used exclusively; the
  ``--no-autofix`` and ``--metrics=off`` flags disable all Semgrep telemetry.
* **Guaranteed cleanup** — this module never creates or deletes temporary
  directories; it only *reads* the extraction path that the caller manages.
* **Path safety** — absolute host paths are stripped before findings are
  persisted; only project-relative paths are stored.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Optional

from app.schemas.finding import FindingSchema, FindingSource, Severity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Timeout for the Semgrep subprocess in seconds.  Configurable for tests.
SEMGREP_TIMEOUT_SECONDS: int = 120

# Path to the bundled Semgrep rule directory, resolved relative to this file.
# Layout:  <project_root>/semgrep_rules/{python,javascript,typescript,java,cpp}.yml
_RULES_DIR: Path = Path(__file__).parent.parent.parent / "semgrep_rules"

# Map Semgrep exit codes to interpretations:
#   0  → success, no findings
#   1  → success, findings found
# Any other code is treated as an error.
_OK_EXIT_CODES = frozenset({0, 1})

# Semgrep severity string → internal Severity enum
_SEVERITY_MAP: dict[str, Severity] = {
    "ERROR": Severity.HIGH,
    "WARNING": Severity.MEDIUM,
    "INFO": Severity.LOW,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_semgrep_executable() -> Optional[str]:
    """Return the path to a working semgrep binary, or None.

    Strategy (in order):
    1. ``shutil.which("semgrep")`` — standard PATH lookup.
    2. A ``semgrep`` script next to the current Python interpreter (venv
       scenario on Windows where the script has no ``.exe`` extension).

    Returns None when semgrep cannot be found or does not respond to
    ``--version`` within 10 seconds.
    """
    # Standard PATH lookup first
    candidate = shutil.which("semgrep")

    # Fallback: venv/Scripts/semgrep (no .exe extension on Windows)
    if candidate is None:
        venv_candidate = Path(sys.executable).parent / "semgrep"
        if venv_candidate.is_file():
            candidate = str(venv_candidate)

    if candidate is None:
        return None

    # Sanity-check: does it actually respond?
    try:
        proc = subprocess.run(
            [candidate, "--version"],
            capture_output=True,
            timeout=10,
        )
        if proc.returncode == 0:
            return candidate
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired, OSError):
        pass

    return None


def _rules_path() -> Optional[Path]:
    """Return the bundled rules directory, or None if it is absent."""
    if _RULES_DIR.is_dir():
        return _RULES_DIR
    logger.warning(
        "Semgrep rules directory not found at %s — skipping Semgrep analysis.",
        _RULES_DIR,
    )
    return None


def _map_severity(semgrep_severity: str) -> Severity:
    """Translate a Semgrep severity string to the internal Severity enum."""
    return _SEVERITY_MAP.get(semgrep_severity.upper(), Severity.LOW)


def _infer_category(rule_id: str) -> str:
    """Infer a broad review category from the rule identifier string."""
    lower = rule_id.lower()
    if any(k in lower for k in (
        "eval", "security", "sql", "injection", "xss", "secret", "password", "passwd",
        "crypto", "auth", "command", "exec", "path", "traversal",
        "overflow", "format", "cwe", "rce", "deserializ",
    )):
        return "Security"
    if any(k in lower for k in ("perf", "performance", "n+1", "loop", "cache")):
        return "Performance"
    if any(k in lower for k in (
        "null", "nullptr", "error", "exception", "crash", "bug",
        "check", "return", "malloc",
    )):
        return "Bug"
    return "Quality"


def _parse_semgrep_json(
    json_text: str,
    extraction_path: Path,
) -> list[FindingSchema]:
    """Parse Semgrep's ``--json`` output into a list of FindingSchema objects.

    Parameters
    ----------
    json_text:
        Raw standard-output from the semgrep process.
    extraction_path:
        The temp directory that was scanned.  Used to relativise absolute
        file paths produced by Semgrep.

    Returns
    -------
    A (possibly empty) list of FindingSchema objects.  Never raises.
    """
    if not json_text or not json_text.strip():
        logger.debug("Semgrep produced empty output.")
        return []

    try:
        data = json.loads(json_text)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Semgrep output is not valid JSON: %s", exc)
        return []

    findings: list[FindingSchema] = []
    results = data.get("results", [])
    if not isinstance(results, list):
        logger.warning("Semgrep JSON 'results' field is not a list.")
        return []

    for item in results:
        if not isinstance(item, dict):
            continue
        try:
            # Relativise the absolute path Semgrep reports
            abs_path = Path(item.get("path", "unknown"))
            try:
                relative_file: str = abs_path.relative_to(extraction_path).as_posix()
            except ValueError:
                # Path outside the extraction root — use basename as fallback
                relative_file = abs_path.name

            extra: dict = item.get("extra", {}) if isinstance(item.get("extra"), dict) else {}
            check_id: str = str(item.get("check_id", "unknown-rule"))
            message: str = str(extra.get("message", check_id))
            severity_str: str = str(extra.get("severity", "INFO"))
            start_info: dict = item.get("start", {}) if isinstance(item.get("start"), dict) else {}
            end_info: dict = item.get("end", {}) if isinstance(item.get("end"), dict) else {}
            start_line: Optional[int] = start_info.get("line")
            end_line: Optional[int] = end_info.get("line")
            # Normalise: end_line == start_line → store as None (single line)
            if end_line == start_line:
                end_line = None
            lines_raw = extra.get("lines", "")
            code_snippet: Optional[str] = lines_raw.strip() if isinstance(lines_raw, str) and lines_raw.strip() else None

            findings.append(
                FindingSchema(
                    id=f"semgrep-{uuid.uuid4().hex[:8]}",
                    agent="Static Analysis (Semgrep)",
                    category=_infer_category(check_id),
                    severity=_map_severity(severity_str),
                    confidence=80,
                    source=FindingSource.STATIC_ANALYSIS,
                    file=relative_file,
                    line_start=start_line,
                    line_end=end_line,
                    title=f"[Semgrep] {check_id}",
                    description=message,
                    impact=f"Detected by Semgrep rule: {check_id}",
                    recommendation=(
                        "Review the flagged code and remediate according to the "
                        "rule description. Consult the rule metadata for CWE references."
                    ),
                    code_snippet=code_snippet,
                    suggested_fix=None,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Skipping malformed Semgrep result item: %s | item=%s", exc, item)
            continue

    return findings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_semgrep(
    extraction_path: Path,
    source_files: dict[str, str],
    *,
    timeout: int = SEMGREP_TIMEOUT_SECONDS,
) -> list[FindingSchema]:
    """Run Semgrep against the extracted source tree and return findings.

    This function is the sole public entry point for the Semgrep integration.
    It is designed to be called from the LangGraph workflow node **after** the
    extraction temp directory has been populated and **before** it is deleted.

    Parameters
    ----------
    extraction_path:
        Filesystem path of the extracted ZIP directory.  Semgrep is pointed at
        this directory so it can resolve multi-file patterns correctly.
    source_files:
        The in-memory ``{relative_path: content}`` mapping produced by
        ``read_source_files()``.  Used only to short-circuit when there is
        nothing to scan.
    timeout:
        Maximum wall-clock seconds to allow Semgrep to run.

    Returns
    -------
    A (possibly empty) list of :class:`~app.schemas.finding.FindingSchema`
    objects tagged ``source=STATIC_ANALYSIS`` and
    ``agent="Static Analysis (Semgrep)"``.

    Notes
    -----
    * **Always returns a list** — never raises, never propagates exceptions.
    * **Does not delete** ``extraction_path`` — cleanup is the caller's
      responsibility (the LangGraph router's ``finally`` block).
    """
    if not source_files:
        logger.debug("Semgrep: no source files to scan.")
        return []

    semgrep_bin = _find_semgrep_executable()
    if semgrep_bin is None:
        logger.info(
            "Semgrep binary not available — cross-language static analysis skipped. "
            "Install semgrep==1.93.0 to enable it."
        )
        return []

    rules = _rules_path()
    if rules is None:
        return []

    try:
        cmd = [
            semgrep_bin,
            "--config", str(rules),
            "--json",
            "--no-git-ignore",
            "--quiet",
            "--metrics=off",
            "--no-autofix",
            str(extraction_path),
        ]
        logger.info("Semgrep: running scan on %s", extraction_path)
        logger.debug("Semgrep command: %s", " ".join(cmd))

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if proc.returncode not in _OK_EXIT_CODES:
            stderr_snippet = (proc.stderr or "")[:500]
            logger.warning(
                "Semgrep exited with unexpected code %d. stderr: %s",
                proc.returncode,
                stderr_snippet,
            )
            return []

        findings = _parse_semgrep_json(proc.stdout, extraction_path)
        logger.info("Semgrep: %d finding(s) found.", len(findings))
        return findings

    except subprocess.TimeoutExpired:
        logger.warning(
            "Semgrep timed out after %d seconds — no findings will be reported.",
            timeout,
        )
        return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("Semgrep analysis raised an unexpected error: %s", exc)
        return []

"""ZIP extraction and source-code reading helpers for repository analysis."""

import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import HTTPException, status

from app.config import get_settings


IGNORED_DIRECTORIES = {".git", "node_modules", "venv", "build", "dist", "__pycache__"}
SOURCE_EXTENSIONS = {".py", ".js", ".ts", ".java", ".cpp", ".cc", ".cxx", ".h", ".hpp"}


def is_ignored_path(file_path: Path) -> bool:
    """Return True when a path belongs to a folder excluded from analysis."""
    return any(part in IGNORED_DIRECTORIES for part in file_path.parts)


def extract_repository_zip(zip_path: str) -> Path:
    """Extract a valid ZIP into a temporary folder and return that folder path."""
    if not zipfile.is_zipfile(zip_path):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ZIP file.")

    extraction_path = Path(tempfile.mkdtemp(prefix="code_review_"))
    maximum_bytes = get_settings().max_extracted_size_mb * 1024 * 1024
    extracted_bytes = 0

    try:
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.infolist():
                relative_path = Path(member.filename.replace("\\", "/"))
                target_path = extraction_path / relative_path
                if member.is_dir() or is_ignored_path(relative_path):
                    continue
                if not target_path.resolve().is_relative_to(extraction_path.resolve()):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="ZIP file contains an unsafe path.",
                    )
                extracted_bytes += member.file_size
                if extracted_bytes > maximum_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Extracted ZIP content is too large.",
                    )
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target_path.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
    except Exception:
        delete_extraction_folder(extraction_path)
        raise

    return extraction_path


def read_source_files(extraction_path: Path) -> dict[str, str]:
    """Read supported source files into a mapping of relative paths to content."""
    source_files: dict[str, str] = {}
    for file_path in extraction_path.rglob("*"):
        if not file_path.is_file() or is_ignored_path(file_path):
            continue
        if file_path.suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        relative_path = file_path.relative_to(extraction_path).as_posix()
        source_files[relative_path] = file_path.read_text(encoding="utf-8", errors="replace")
    return source_files


def delete_extraction_folder(extraction_path: Path) -> None:
    """Remove the temporary extraction folder after code analysis finishes."""
    shutil.rmtree(extraction_path, ignore_errors=True)
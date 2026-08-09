"""Safe local storage helpers for uploaded repository ZIP files."""

from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.config import get_settings


CHUNK_SIZE = 1024 * 1024


async def save_uploaded_zip(uploaded_file: UploadFile) -> tuple[str, str]:
    """Validate and save a ZIP upload, returning its display name and file path."""
    original_name = uploaded_file.filename or ""
    if Path(original_name).suffix.lower() != ".zip":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only ZIP files are accepted.",
        )

    settings = get_settings()
    upload_folder = Path(settings.upload_directory)
    upload_folder.mkdir(parents=True, exist_ok=True)
    stored_path = upload_folder / f"{uuid4()}.zip"
    maximum_bytes = settings.max_upload_size_mb * 1024 * 1024
    bytes_written = 0

    try:
        with stored_path.open("wb") as zip_file:
            while chunk := await uploaded_file.read(CHUNK_SIZE):
                bytes_written += len(chunk)
                if bytes_written > maximum_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"ZIP file must be at most {settings.max_upload_size_mb} MB.",
                    )
                zip_file.write(chunk)
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise
    finally:
        await uploaded_file.close()

    return Path(original_name).stem, str(stored_path)


def delete_uploaded_zip(zip_path: str) -> None:
    """Delete a stored ZIP file when its repository record is deleted."""
    Path(zip_path).unlink(missing_ok=True)
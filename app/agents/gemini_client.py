"""Small wrapper around the Gemini SDK used by all review agents."""

import logging

from google import genai

from app.config import get_settings


logger = logging.getLogger(__name__)


def format_source_files(source_files: dict[str, str]) -> str:
    """Combine source files into a clearly labeled prompt section for Gemini."""
    return "\n\n".join(
        f"FILE: {file_path}\n```\n{content}\n```"
        for file_path, content in source_files.items()
    )


def generate_text(prompt: str) -> str:
    """Send one prompt to Gemini and return its text response, retrying on rate limits."""
    import time
    settings = get_settings()
    client = genai.Client(api_key=settings.gemini_api_key)

    max_retries = 6
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=prompt,
            )
            break
        except Exception as error:
            error_str = str(error)
            # Retry on rate limit (429), server overload (503), or UNAVAILABLE
            is_retryable = (
                "429" in error_str
                or "503" in error_str
                or "RESOURCE_EXHAUSTED" in error_str
                or "UNAVAILABLE" in error_str
                or "high demand" in error_str
            )
            if is_retryable and attempt < max_retries - 1:
                wait_seconds = 20 * (attempt + 1)
                logger.warning(
                    "Gemini temporarily unavailable (attempt %s/%s). Waiting %s seconds before retry...",
                    attempt + 1, max_retries, wait_seconds
                )
                time.sleep(wait_seconds)
                continue
            logger.exception("Gemini code review request failed.")
            raise RuntimeError("The AI code review could not be completed.") from error

    if not response.text:
        raise RuntimeError("The AI code review returned an empty response.")
    return response.text


def generate_agent_report(instructions: str, source_files: dict[str, str]) -> str:
    """Send a focused code-review prompt to Gemini and return its text response."""
    prompt = f"{instructions}\n\nSOURCE CODE:\n{format_source_files(source_files)}"
    return generate_text(prompt)
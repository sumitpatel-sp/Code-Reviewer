"""Application settings loaded from environment variables."""

from functools import lru_cache
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Keep all environment-based settings in one simple object."""

    app_name: str = "AI Multi-Agent Code Review Platform"
    environment: str = "development"
    debug: bool = False

    mysql_host: str
    mysql_port: int = 3306
    mysql_database: str
    mysql_user: str
    mysql_password: str
    mysql_root_password: str

    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    gemini_api_key: str
    gemini_model: str = "gemini-2.0-flash"
    upload_directory: str = "app/uploads"
    max_upload_size_mb: int = 25
    max_extracted_size_mb: int = 100

    # Read values from .env locally, while Docker supplies the same values directly.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def database_url(self) -> str:
        """Build the MySQL connection URL required by SQLAlchemy.

        The password is URL-encoded so that special characters such as '@'
        do not confuse the URL parser.
        """
        encoded_password = quote(self.mysql_password, safe="")
        return (
            f"mysql+pymysql://{self.mysql_user}:{encoded_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
        )


@lru_cache
def get_settings() -> Settings:
    """Create settings once and reuse them for the lifetime of the application."""
    return Settings()

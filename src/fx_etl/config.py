"""Runtime configuration, loaded from environment variables or a .env file.

All settings are prefixed with FX_ so they do not clash with anything else in
the environment. Sensible defaults mean the pipeline runs with no setup at all
against a local SQLite file.
"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///fx.db"
    api_base_url: str = "https://api.frankfurter.dev/v1"
    base_currency: str = "USD"
    symbols: list[str] = Field(default_factory=lambda: ["EUR", "GBP", "JPY", "CNY", "ETB"])

    request_timeout: float = 30.0
    max_retries: int = 4

    log_level: str = "INFO"

    @field_validator("symbols", mode="before")
    @classmethod
    def _split_symbols(cls, value: object) -> object:
        """Allow FX_SYMBOLS to be given as a comma-separated string."""
        if isinstance(value, str):
            return [part.strip().upper() for part in value.split(",") if part.strip()]
        return value

    @field_validator("base_currency")
    @classmethod
    def _upper_base(cls, value: str) -> str:
        return value.strip().upper()


def get_settings() -> Settings:
    """Return a fresh Settings instance read from the environment."""
    return Settings()

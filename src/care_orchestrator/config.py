"""
Configuration module for care-orchestrator.

Loads settings from environment variables / .env file using pydantic-settings.
All configurable parameters are centralized here.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Anthropic API
    anthropic_api_key: str = ""
    model_name: str = "claude-sonnet-4-20250514"
    max_tokens: int = 2048

    # Logging
    log_level: str = "INFO"
    log_file: str = "logs/audit.log"

    # Paths
    guardrails_path: Path = Path("config/regulatory_guardrails.xml")


# Singleton settings instance
settings = Settings()

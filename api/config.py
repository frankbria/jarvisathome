"""
Configuration management for the API.
"""

import os
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # API Keys
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 4

    # Job Management
    max_job_age_minutes: int = 5
    cleanup_interval_minutes: int = 10

    # Logging
    log_level: str = "INFO"

    # CORS Settings
    allowed_origins: List[str] = ["*"]

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def is_anthropic_configured(self) -> bool:
        """Check if Anthropic API key is set"""
        return bool(self.anthropic_api_key)

    @property
    def is_openai_configured(self) -> bool:
        """Check if OpenAI API key is set"""
        return bool(self.openai_api_key)


# Global settings instance
settings = Settings()

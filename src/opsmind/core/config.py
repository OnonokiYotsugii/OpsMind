"""Read validated configuration without opening external connections."""

from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment variables override values in the local .env file."""

    model_config = SettingsConfigDict(
        env_prefix="OPSMIND_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    # Optional in P0; database startup will validate its presence in P1.
    database_url: SecretStr = SecretStr("")

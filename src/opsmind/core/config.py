"""Validated environment settings; credentials never appear in repr."""

from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPSMIND_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: SecretStr = SecretStr("")
    migration_database_url: SecretStr = SecretStr("")
    test_database_url: SecretStr = SecretStr("")
    demo_employee_no: str = Field(default="EMP-1001", pattern=r"^[A-Z0-9_-]{1,64}$")

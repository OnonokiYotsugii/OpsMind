"""Validated environment settings; credentials never appear in repr."""

from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPSMIND_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: SecretStr = SecretStr("")
    migration_database_url: SecretStr = SecretStr("")
    test_database_url: SecretStr = SecretStr("")
    demo_employee_no: str = Field(default="EMP-1001", pattern=r"^[A-Z0-9_-]{1,64}$")

    llm_provider: Literal["deepseek", "openai_compatible"] = "deepseek"
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = Field(default="deepseek-v4-pro", pattern=r"^[A-Za-z0-9._:/-]{1,128}$")
    llm_api_key: SecretStr = SecretStr("")
    llm_timeout_seconds: float = Field(default=30, gt=0, le=120)
    llm_total_timeout_seconds: float = Field(default=60, gt=0, le=180)
    llm_max_retries: int = Field(default=1, ge=0, le=3)
    llm_max_output_tokens: int = Field(default=1500, ge=128, le=8192)

    @field_validator("llm_base_url")
    @classmethod
    def validate_llm_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
        ):
            raise ValueError("Use an HTTPS base URL without credentials, query or fragment.")
        return value.rstrip("/")

    agent_max_steps: int = Field(default=6, ge=1, le=20)
    agent_max_tool_calls: int = Field(default=8, ge=1, le=30)
    agent_timeout_seconds: int = Field(default=120, ge=5, le=300)
    agent_approval_ttl_seconds: int = Field(default=1800, ge=60, le=86400)

    rag_model_cache: str = ".cache/embeddings"
    rag_index_path: str = ".data/chroma"
    rag_max_distance: float = Field(default=0.22, ge=0, le=2)

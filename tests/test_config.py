import pytest
from pydantic import ValidationError

from opsmind.core.config import Settings


def test_environment_overrides_dotenv(tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text("OPSMIND_LOG_LEVEL=WARNING\n", encoding="utf-8")
    monkeypatch.setenv("OPSMIND_LOG_LEVEL", "ERROR")
    assert Settings(_env_file=dotenv).log_level == "ERROR"


def test_invalid_log_level_fails_early(monkeypatch):
    monkeypatch.setenv("OPSMIND_LOG_LEVEL", "VERBOSE")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_database_credentials_are_hidden_in_representations(monkeypatch):
    monkeypatch.setenv("OPSMIND_DATABASE_URL", "mysql+pymysql://user:private-password@localhost/db")
    settings = Settings(_env_file=None)
    assert "private-password" not in repr(settings)
    assert "private-password" not in settings.model_dump_json()

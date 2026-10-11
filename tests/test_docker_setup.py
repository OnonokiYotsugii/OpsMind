import importlib.util
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

from opsmind.core.config import Settings

spec = importlib.util.spec_from_file_location("setup_docker", Path("scripts/setup_docker.py"))
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def test_container_credentials_are_separate_and_not_overwritten(tmp_path):
    target = tmp_path / "docker"
    setup.generate(target, Settings(_env_file=None, llm_api_key="synthetic$secret"))
    app = dotenv_values(target / "app.env")
    migration = dotenv_values(target / "migration.env")
    url = make_url(app["OPSMIND_DATABASE_URL"])
    migration_url = make_url(migration["OPSMIND_MIGRATION_DATABASE_URL"])
    assert (url.host, url.database, url.username) == ("db", "opsmind_demo", "opsmind_app")
    assert url.password != migration_url.password
    assert "OPSMIND_MIGRATION_DATABASE_URL" not in app
    assert "OPSMIND_LLM_API_KEY" not in migration
    assert app["OPSMIND_LLM_API_KEY"] == "synthetic$secret"
    sql = (target / "init.sql").read_text()
    assert "GRANT SELECT, INSERT, UPDATE ON opsmind_demo.* TO 'opsmind_app'" in sql
    assert "GRANT ALL PRIVILEGES ON opsmind_demo.* TO 'opsmind_migrate'" in sql
    before = {p.name: p.read_bytes() for p in target.iterdir()}
    with pytest.raises(FileExistsError):
        setup.generate(target, Settings(_env_file=None))
    assert before == {p.name: p.read_bytes() for p in target.iterdir()}


def test_invalid_secret_does_not_leave_partial_configuration(tmp_path):
    target = tmp_path / "docker"
    with pytest.raises(ValueError, match="unsupported"):
        setup.generate(target, Settings(_env_file=None, llm_api_key="bad\nvalue"))
    assert not target.exists()

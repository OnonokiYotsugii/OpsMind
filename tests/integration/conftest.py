from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from alembic import command
from opsmind.api.dependencies import get_session
from opsmind.core.config import Settings
from opsmind.db.seed import seed_demo
from opsmind.db.session import create_db_engine, validated_mysql_url
from opsmind.main import create_app


@pytest.fixture(scope="session")
def mysql_engine(request):
    if not request.config.getoption("--mysql"):
        pytest.skip("Run pytest --mysql with OPSMIND_TEST_DATABASE_URL configured.")
    settings = Settings()
    raw = settings.test_database_url.get_secret_value()
    try:
        url = validated_mysql_url(raw)
    except ValueError:
        pytest.fail("Configure OPSMIND_TEST_DATABASE_URL locally before --mysql.", pytrace=False)
    if url.database != "opsmind_test" or url.host not in {"localhost", "127.0.0.1"}:
        pytest.fail("Integration tests require local database opsmind_test.", pytrace=False)
    for normal_raw in (
        settings.database_url.get_secret_value(),
        settings.migration_database_url.get_secret_value(),
    ):
        if normal_raw and validated_mysql_url(normal_raw).database == url.database:
            pytest.fail(
                "Test database must differ from application/migration database.", pytrace=False
            )
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.attributes["database_url"] = raw
    command.upgrade(config, "head")
    command.check(config)
    engine = create_db_engine(raw)
    yield engine
    engine.dispose()


@pytest.fixture
def db_connection(mysql_engine):
    with mysql_engine.connect() as connection:
        transaction = connection.begin()
        with Session(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        ) as session:
            seed_demo(session)
        try:
            yield connection
        finally:
            transaction.rollback()


@pytest.fixture
def client(db_connection):
    app = create_app(Settings(_env_file=None, database_url="", demo_employee_no="EMP-1001"))

    def session_override():
        with Session(
            bind=db_connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        ) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as client:
        yield client

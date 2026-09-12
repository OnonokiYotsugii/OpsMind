import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError, OperationalError

from opsmind.api.dependencies import get_session
from opsmind.core.config import Settings
from opsmind.main import create_app


def test_missing_database_returns_clear_error():
    with TestClient(create_app(Settings(_env_file=None, database_url=""))) as client:
        result = client.get("/api/v1/equipment/EQ-10023")
        assert result.status_code == 503
        assert result.json()["error"]["code"] == "database_unavailable"


@pytest.mark.parametrize(
    "exception,status",
    [
        (IntegrityError("INSERT secret_sql", {"password": "secret"}, Exception("private")), 409),
        (OperationalError("SELECT secret_sql", {}, Exception("private")), 503),
        (OperationalError("UPDATE secret_sql", {}, Exception(3819, "private")), 409),
    ],
)
def test_database_error_response_does_not_leak_details(exception, status):
    app = create_app(Settings(_env_file=None, database_url=""))

    def failing_session():
        raise exception

    app.dependency_overrides[get_session] = failing_session
    with TestClient(app) as client:
        result = client.get("/api/v1/equipment/EQ-10023")
        assert result.status_code == status
        assert "secret" not in result.text
        assert "private" not in result.text


def test_demo_cannot_start_as_production():
    with pytest.raises(ValueError, match="demo identity"):
        create_app(Settings(_env_file=None, environment="production"))

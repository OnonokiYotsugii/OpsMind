from fastapi.testclient import TestClient

from opsmind.core.config import Settings
from opsmind.main import create_app


def test_health_works_without_database():
    app = create_app(Settings(_env_file=None, database_url=""))
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

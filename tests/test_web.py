from fastapi.testclient import TestClient

from opsmind.core.config import Settings
from opsmind.main import create_app


def test_home_and_assets_without_database_or_model():
    with TestClient(create_app(Settings(_env_file=None, database_url=""))) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "运维工作台" in page.text
        assert page.headers["content-type"].startswith("text/html")
        for asset in ("app.js", "app.css"):
            assert client.get(f"/assets/{asset}").status_code == 200
        assert client.get("/assets/.env").status_code == 404
        assert client.get("/assets/%2e%2e/core/config.py").status_code == 404
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/api/v1/agent/runs/invalid").status_code in {422, 503}

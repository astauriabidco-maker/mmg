from fastapi.testclient import TestClient

from backend.main import app


def test_health_endpoints_are_available():
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "database": "ok"}

from fastapi.testclient import TestClient


def test_fastapi_app_imports():
    from backend.main import app

    assert app.title == "Atelier Menuiserie V1 Pro"


def test_token_rejects_invalid_request_without_crashing():
    from backend.main import app

    client = TestClient(app)
    response = client.post("/token", data={})

    assert 400 <= response.status_code < 500
    assert "detail" in response.json()


def test_sensitive_routes_require_authentication():
    from backend.main import app

    client = TestClient(app)

    responses = [
        client.get("/v2/config/stations"),
        client.get("/v2/stock/products"),
        client.get("/v2/planning/PVC_DEBIT"),
        client.post("/production/start", json={}),
    ]

    assert [response.status_code for response in responses] == [401, 401, 401, 401]

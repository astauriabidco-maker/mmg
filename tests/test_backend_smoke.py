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
        client.get("/v2/stock/locations"),
        client.get("/v2/stock/quants"),
        client.get("/v2/analytics/kpi"),
        client.get("/v2/analytics/workshop"),
        client.get("/v2/sales/"),
        client.get("/v2/accounting/invoices"),
        client.get("/v2/logistics/routes"),
        client.get("/v2/purchases/"),
        client.get("/v2/suppliers/"),
        client.get("/v2/partners/clients"),
        client.get("/v2/pos/items"),
        client.get("/v2/pos/sessions/active"),
        client.get("/v2/planning/PVC_DEBIT"),
        client.post("/production/start", json={}),
    ]

    assert [response.status_code for response in responses] == [401] * len(responses)


def test_sales_signature_portal_remains_public():
    from backend.main import app

    client = TestClient(app)
    response = client.get("/v2/sales/portal/not-a-real-token")

    assert response.status_code == 404

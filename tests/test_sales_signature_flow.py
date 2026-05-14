import pytest
import sys
from fastapi.testclient import TestClient
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend import database, models
from backend.core.security import get_password_hash
from backend.main import app


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[database.get_db] = override_get_db

    with TestingSessionLocal() as db:
        db.add(
            models.User(
                username="admin",
                pin_hash=get_password_hash("1234"),
                role="ADMIN",
                is_active=True,
            )
        )
        db.commit()

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def _admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/token",
        data={"username": "admin", "password": "1234"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_sales_signature_flow_creates_invoice_from_public_portal(client: TestClient):
    admin_headers = _admin_headers(client)

    create_response = client.post(
        "/v2/sales/",
        json={
            "client_name": "ACME Renovation",
            "client_contact": "Alice Martin",
            "client_email": "alice@example.test",
            "client_address": "12 rue des Ateliers, 75001 Paris",
            "validity_days": 21,
            "tax_rate": 20.0,
            "currency": "EUR",
            "notes": "Pose incluse.",
            "lines": [
                {
                    "variant_id": None,
                    "description": "Baie coulissante aluminium",
                    "quantity": 2,
                    "unit_price": 1500.0,
                    "discount_pct": 0,
                    "visual_config": None,
                },
                {
                    "variant_id": None,
                    "description": "Motorisation volet",
                    "quantity": 1,
                    "unit_price": 600.0,
                    "discount_pct": 0,
                    "visual_config": None,
                },
            ],
        },
        headers=admin_headers,
    )
    assert create_response.status_code == 200, create_response.text
    sale_order = create_response.json()
    assert sale_order["status"] == "DRAFT"
    assert sale_order["signature_token"] is None

    sent_response = client.put(
        f"/v2/sales/{sale_order['id']}/status",
        params={"status": "SENT"},
        headers=admin_headers,
    )
    assert sent_response.status_code == 200, sent_response.text
    portal_link = sent_response.json()["portal_link"]
    assert portal_link

    refreshed_response = client.get(
        f"/v2/sales/{sale_order['id']}",
        headers=admin_headers,
    )
    assert refreshed_response.status_code == 200, refreshed_response.text
    sent_order = refreshed_response.json()
    signature_token = sent_order["signature_token"]
    assert sent_order["status"] == "SENT"
    assert signature_token
    assert portal_link.endswith(f"/portal/sign/{signature_token}")

    public_response = client.get(f"/v2/sales/portal/{signature_token}")
    assert public_response.status_code == 200, public_response.text
    public_quote = public_response.json()
    assert public_quote["client_name"] == "ACME Renovation"
    assert public_quote["status"] == "SENT"
    assert len(public_quote["lines"]) == 2

    sign_response = client.post(f"/v2/sales/portal/{signature_token}/sign")
    assert sign_response.status_code == 200, sign_response.text

    signed_response = client.get(
        f"/v2/sales/{sale_order['id']}",
        headers=admin_headers,
    )
    assert signed_response.status_code == 200, signed_response.text
    signed_order = signed_response.json()
    assert signed_order["status"] == "VALIDATED"
    assert signed_order["signed_at"] is not None
    assert signed_order["signed_by_ip"]
    assert "SIGNATURE" in signed_order["notes"]

    invoices_response = client.get("/v2/accounting/invoices", headers=admin_headers)
    assert invoices_response.status_code == 200, invoices_response.text
    invoices = invoices_response.json()
    assert len(invoices) == 1

    invoice = invoices[0]
    assert invoice["reference"].startswith("F-")
    assert invoice["client_name"] == "ACME Renovation"
    assert invoice["client_address"] == "12 rue des Ateliers, 75001 Paris"
    assert invoice["status"] == "UNPAID"
    assert invoice["subtotal"] == 3600.0
    assert invoice["tax_rate"] == 20.0
    assert invoice["tax_amount"] == 720.0
    assert invoice["total"] == 4320.0
    assert invoice["qr_code_hash"]
    assert [line["description"] for line in invoice["lines"]] == [
        "Baie coulissante aluminium",
        "Motorisation volet",
    ]

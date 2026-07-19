import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
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


def _login(client: TestClient) -> dict:
    response = client.post("/token", data={"username": "admin", "password": "1234"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_suppliers_api_requires_authentication(client):
    assert client.get("/v2/suppliers/").status_code == 401


def test_legacy_partners_suppliers_route_is_removed(client):
    headers = _login(client)
    assert client.get("/v2/partners/suppliers", headers=headers).status_code == 404
    assert client.post("/v2/partners/suppliers", json={"name": "X"}, headers=headers).status_code == 404


def test_suppliers_crud_with_business_profile(client):
    headers = _login(client)

    payload = {
        "name": "ALU PRO",
        "contact_name": "Sophie Martin",
        "email": "contact@alupro.fr",
        "country": "France",
        "tax_id": "FR123456789",
        "supplier_status": "STRATEGIC",
        "supplier_category": "ALUMINIUM",
        "default_currency": "EUR",
        "incoterm": "DAP",
        "delivery_terms": "Franco palette",
        "lead_time_days": 15,
    }
    created = client.post("/v2/suppliers/", json=payload, headers=headers)
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["supplier_status"] == "STRATEGIC"
    assert body["supplier_category"] == "ALUMINIUM"
    assert body["incoterm"] == "DAP"
    assert body["delivery_terms"] == "Franco palette"
    assert body["default_currency"] == "EUR"
    supplier_id = body["id"]

    # Doublon de nom refusé
    duplicate = client.post("/v2/suppliers/", json={"name": "ALU PRO"}, headers=headers)
    assert duplicate.status_code == 400

    # Valeurs par défaut du profil business
    defaulted = client.post("/v2/suppliers/", json={"name": "QUINCAILLERIE EXPRESS"}, headers=headers)
    assert defaulted.status_code == 200, defaulted.text
    assert defaulted.json()["supplier_status"] == "ACTIVE"
    assert defaulted.json()["default_currency"] == "EUR"

    # Mise à jour
    updated = client.put(
        f"/v2/suppliers/{supplier_id}",
        json={**payload, "supplier_status": "BLOCKED", "incoterm": "EXW"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["supplier_status"] == "BLOCKED"
    assert updated.json()["incoterm"] == "EXW"

    # Liste triée par nom
    listed = client.get("/v2/suppliers/", headers=headers)
    assert listed.status_code == 200
    names = [s["name"] for s in listed.json()]
    assert names == sorted(names)
    assert "ALU PRO" in names

    # Suppression logique : le fournisseur disparaît de la liste
    deleted = client.delete(f"/v2/suppliers/{supplier_id}", headers=headers)
    assert deleted.status_code == 200
    listed_after = client.get("/v2/suppliers/", headers=headers)
    assert "ALU PRO" not in [s["name"] for s in listed_after.json()]

    # ID inconnu
    assert client.get("/v2/suppliers/", headers=headers).status_code == 200
    assert client.delete("/v2/suppliers/99999", headers=headers).status_code == 404

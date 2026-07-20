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
        db.add(
            models.User(
                username="operateur",
                pin_hash=get_password_hash("1111"),
                role="OPERATOR",
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


def _login(client: TestClient, username: str, password: str) -> dict:
    response = client.post("/token", data={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _default_stages():
    return [
        {"id": "DRAFT", "title": "Brouillons"},
        {"id": "SENT", "title": "Envoyés (Négo)"},
        {"id": "VALIDATED", "title": "Gagnés (Signés)"},
        {"id": "IN_DESIGN", "title": "Bureau d'Études"},
        {"id": "READY_FOR_PROD", "title": "Prêts pour Prod"},
        {"id": "IN_PRODUCTION", "title": "En Production"},
    ]


def test_save_stages_persists_reorder_and_custom_stage(client):
    headers = _login(client, "admin", "1234")

    new_stages = _default_stages()
    # Réordonnancement : VALIDATED en tête + étape personnalisée
    validated = new_stages.pop(2)
    new_stages.insert(0, validated)
    new_stages.append({"id": "STAGE_CUSTOM_1", "title": "Attente acompte"})

    response = client.post("/v2/sales/stages", json=new_stages, headers=headers)
    assert response.status_code == 200, response.text

    persisted = client.get("/v2/sales/stages", headers=headers)
    assert persisted.status_code == 200
    assert persisted.json() == new_stages


def test_save_stages_rejects_system_stage_deletion(client):
    headers = _login(client, "admin", "1234")

    stages_without_draft = [s for s in _default_stages() if s["id"] != "DRAFT"]
    response = client.post("/v2/sales/stages", json=stages_without_draft, headers=headers)
    assert response.status_code == 400
    assert "DRAFT" in response.json()["detail"]


def test_save_stages_requires_admin_or_manager(client):
    assert client.post("/v2/sales/stages", json=_default_stages()).status_code == 401

    operator_headers = _login(client, "operateur", "1111")
    response = client.post("/v2/sales/stages", json=_default_stages(), headers=operator_headers)
    assert response.status_code == 403

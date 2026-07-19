import shutil
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

PNG_1PX = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAD"
    "UlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture()
def client(monkeypatch):
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

    # Evite d'ecrire l'export CSV Proges sur le disque pendant les tests
    from backend.services import mmg_to_proges

    monkeypatch.setattr(mmg_to_proges, "save_proges_export", lambda data: None)

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)
        # Nettoyage des fichiers uploades pendant le test
        shutil.rmtree(ROOT_DIR / "uploads" / "mmg", ignore_errors=True)


def _login(test_client: TestClient) -> dict:
    response = test_client.post("/token", data={"username": "admin", "password": "1234"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _mmg_payload() -> dict:
    return {
        "client": {
            "name": "Client Test",
            "contact": "0600000000",
            "address": "1 rue du Test",
            "site_address": "2 rue du Chantier",
            "email": "client@test.fr",
            "client_type": "PARTICULIER",
        },
        "measurements": {"width_mm": 1200, "height_mm": 1400, "passage_height_mm": 1350},
        "options": {"sill_height_mm": 900, "transom_height_mm": None, "shutter_type": "gauche"},
        "configuration": {
            "view": "interior",
            "opening_type": "tirant",
            "opening_side": "gauche",
            "sash_count": 2,
            "material": "ALU",
            "product_series": "Standard",
            "color_ral": "7016",
        },
        "logistics": {"floor_number": 1, "access_difficulty": "Standard", "environment": "Standard"},
        "photos": [PNG_1PX],
        "signature": PNG_1PX,
    }


def test_mmg_creation_photo_upload_and_static_serving(client):
    headers = _login(client)

    # Creation avec photo + signature base64
    response = client.post("/v2/mmg/", json=_mmg_payload(), headers=headers)
    assert response.status_code == 200, response.text
    dossier = response.json()
    assert dossier["reference"].startswith("MMG-")
    assert dossier["status"] == "SENT"

    # Detail : URLs d'uploads servies sous /uploads/mmg/
    detail_resp = client.get(f"/v2/mmg/{dossier['id']}", headers=headers)
    assert detail_resp.status_code == 200, detail_resp.text
    detail = detail_resp.json()
    assert len(detail["photos"]) == 1
    assert detail["photos"][0].startswith("/uploads/mmg/photos/")
    assert detail["signature"].startswith("/uploads/mmg/signatures/")
    assert "order_id" in detail

    # Les fichiers sont reellement servis par le montage statique /uploads
    photo_resp = client.get(detail["photos"][0])
    assert photo_resp.status_code == 200
    assert len(photo_resp.content) > 0

    # Liste enrichie (champs client requis par le dashboard CRM)
    list_resp = client.get("/v2/mmg/", headers=headers)
    assert list_resp.status_code == 200
    listed = list_resp.json()[0]
    assert listed["client_contact"] == "0600000000"
    assert listed["client_address"] == "1 rue du Test"


def test_mmg_status_and_send_quote_flow(client):
    headers = _login(client)
    dossier = client.post("/v2/mmg/", json=_mmg_payload(), headers=headers).json()

    # Changement de statut (PATCH, contrat MMGStatusUpdate)
    bad = client.patch(f"/v2/mmg/{dossier['id']}/status", json={"status": "BOGUS"}, headers=headers)
    assert bad.status_code == 422

    ok = client.patch(f"/v2/mmg/{dossier['id']}/status", json={"status": "VALIDATED"}, headers=headers)
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "VALIDATED"

    # Envoi du devis : cree un SaleOrder et horodate le dossier
    quote = client.post(f"/v2/mmg/{dossier['id']}/send-quote", headers=headers)
    assert quote.status_code == 200, quote.text
    assert "sent_at" in quote.json()

    detail = client.get(f"/v2/mmg/{dossier['id']}", headers=headers).json()
    assert detail["sale_order_id"] is not None
    assert detail["quote_sent_at"] is not None

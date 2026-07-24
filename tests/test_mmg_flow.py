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


def test_mmg_links_crm_client_structured_site_and_implicit_mission(client):
    headers = _login(client)
    crm_response = client.post(
        "/v2/partners/clients",
        json={
            "name": "Client CRM Métré",
            "contact_name": "Mme Chantier",
            "email": "chantier@example.fr",
            "phone": "0611223344",
            "address": "10 rue de Facturation",
            "country": "FR",
            "customer_type": "B2C",
            "is_active": True,
        },
        headers=headers,
    )
    assert crm_response.status_code == 200, crm_response.text
    crm_client = crm_response.json()

    payload = _mmg_payload()
    payload["client_id"] = crm_client["id"]
    payload["site"] = {
        "client_id": crm_client["id"],
        "label": "Maison principale",
        "address_line1": "25 avenue du Chantier",
        "postal_code": "75012",
        "city": "Paris",
        "country": "FR",
        "contact_name": "M. Accès",
        "contact_phone": "0699887766",
        "access_instructions": "Portail bleu, appeler avant.",
        "is_default": True,
    }
    response = client.post("/v2/mmg/", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    dossier = response.json()
    assert dossier["client_id"] == crm_client["id"]
    assert dossier["site_address_id"] is not None
    assert dossier["measure_mission_id"] is not None

    detail = client.get(f"/v2/mmg/{dossier['id']}", headers=headers).json()
    assert detail["client_name"] == "Client CRM Métré"
    assert detail["site_address"] == "25 avenue du Chantier, 75012 Paris, FR"

    sites = client.get(
        "/v2/mmg/sites",
        params={"client_id": crm_client["id"]},
        headers=headers,
    ).json()
    assert len(sites) == 1
    assert sites[0]["city"] == "Paris"
    assert sites[0]["access_instructions"] == "Portail bleu, appeler avant."

    mission = client.get(
        f"/v2/mmg/missions/{dossier['measure_mission_id']}",
        headers=headers,
    ).json()
    assert mission["status"] == "TO_REVIEW"
    assert mission["dossier_ids"] == [dossier["id"]]
    assert mission["site"]["postal_code"] == "75012"


def test_measure_mission_status_machine_rejects_skipped_review(client):
    headers = _login(client)
    crm_client = client.post(
        "/v2/partners/clients",
        json={
            "name": "Client Mission",
            "email": "mission@example.fr",
            "phone": "0601020304",
            "address": "1 rue Mission",
            "country": "FR",
            "customer_type": "B2B",
            "is_active": True,
        },
        headers=headers,
    ).json()
    response = client.post(
        "/v2/mmg/missions",
        json={
            "client_id": crm_client["id"],
            "site": {
                "address_line1": "2 rue du Site",
                "postal_code": "69001",
                "city": "Lyon",
                "country": "FR",
            },
            "purpose": "Remplacement de trois fenêtres",
            "assigned_user_id": 1,
            "scheduled_start": "2026-08-03T08:00:00",
            "scheduled_end": "2026-08-03T10:00:00",
            "status": "DRAFT",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    mission = response.json()
    assert mission["reference"].startswith("MET-")

    to_schedule = client.patch(
        f"/v2/mmg/missions/{mission['id']}/status",
        json={"status": "TO_SCHEDULE"},
        headers=headers,
    )
    assert to_schedule.status_code == 200
    scheduled = client.patch(
        f"/v2/mmg/missions/{mission['id']}/status",
        json={"status": "SCHEDULED"},
        headers=headers,
    )
    assert scheduled.status_code == 200

    invalid = client.patch(
        f"/v2/mmg/missions/{mission['id']}/status",
        json={"status": "VALIDATED"},
        headers=headers,
    )
    assert invalid.status_code == 409
    assert "Transition de mission interdite" in invalid.text


def test_measure_mission_multi_openings_and_be_review(client):
    headers = _login(client)
    crm_client = client.post(
        "/v2/partners/clients",
        json={
            "name": "Client Multi Ouvrages",
            "email": "multi@example.fr",
            "phone": "0600001122",
            "address": "1 rue des Ouvrages",
            "country": "FR",
            "customer_type": "B2C",
            "is_active": True,
        },
        headers=headers,
    ).json()
    mission_response = client.post(
        "/v2/mmg/missions",
        json={
            "client_id": crm_client["id"],
            "site": {
                "address_line1": "8 rue du Chantier",
                "postal_code": "33000",
                "city": "Bordeaux",
                "country": "FR",
            },
            "assigned_user_id": 1,
            "scheduled_start": "2026-08-10T09:00:00",
            "scheduled_end": "2026-08-10T11:00:00",
            "purpose": "Relevé de deux menuiseries",
            "status": "SCHEDULED",
        },
        headers=headers,
    )
    assert mission_response.status_code == 200, mission_response.text
    mission = mission_response.json()

    started = client.patch(
        f"/v2/mmg/missions/{mission['id']}/status",
        json={"status": "ON_SITE"},
        headers=headers,
    )
    assert started.status_code == 200, started.text

    for label, room, width, height in (
        ("F01", "Séjour", 1200, 1400),
        ("PF01", "Cuisine", 1800, 2150),
    ):
        opening = client.post(
            f"/v2/mmg/missions/{mission['id']}/openings",
            json={
                "label": label,
                "room": room,
                "product_type": "WINDOW",
                "width_mm": width,
                "height_mm": height,
                "material": "ALU",
                "sash_count": 2,
                "status": "COMPLETE",
            },
            headers=headers,
        )
        assert opening.status_code == 200, opening.text

    review = client.patch(
        f"/v2/mmg/missions/{mission['id']}/status",
        json={"status": "TO_REVIEW"},
        headers=headers,
    )
    assert review.status_code == 200, review.text
    assert review.json()["status"] == "TO_REVIEW"
    assert len(review.json()["openings"]) == 2
    assert all(opening["status"] == "TO_REVIEW" for opening in review.json()["openings"])

    validated = client.patch(
        f"/v2/mmg/missions/{mission['id']}/status",
        json={"status": "VALIDATED"},
        headers=headers,
    )
    assert validated.status_code == 200, validated.text
    assert all(opening["status"] == "VALIDATED" for opening in validated.json()["openings"])


def test_measure_mission_rejects_incomplete_opening_for_review(client):
    headers = _login(client)
    crm_client = client.post(
        "/v2/partners/clients",
        json={
            "name": "Client Relevé Incomplet",
            "phone": "0600003344",
            "country": "FR",
            "customer_type": "B2C",
            "is_active": True,
        },
        headers=headers,
    ).json()
    mission = client.post(
        "/v2/mmg/missions",
        json={
            "client_id": crm_client["id"],
            "site": {
                "address_line1": "3 rue du Relevé",
                "postal_code": "44000",
                "city": "Nantes",
                "country": "FR",
            },
            "assigned_user_id": 1,
            "scheduled_start": "2026-08-11T09:00:00",
            "status": "SCHEDULED",
        },
        headers=headers,
    ).json()
    client.patch(
        f"/v2/mmg/missions/{mission['id']}/status",
        json={"status": "ON_SITE"},
        headers=headers,
    )
    opening = client.post(
        f"/v2/mmg/missions/{mission['id']}/openings",
        json={"label": "F01", "status": "DRAFT"},
        headers=headers,
    )
    assert opening.status_code == 200, opening.text
    review = client.patch(
        f"/v2/mmg/missions/{mission['id']}/status",
        json={"status": "TO_REVIEW"},
        headers=headers,
    )
    assert review.status_code == 422
    assert "Tous les ouvrages" in review.text


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


def _mmg_payload_full_options() -> dict:
    payload = _mmg_payload()
    payload["configuration"].update(
        {
            "installation_type": "Neuf",
            "doublage_thickness": "100",
            "shape": "Cintré",
            "ventilation": "Acoustique",
            "soubassement_type": "Plein",
        }
    )
    payload["annexes"] = {
        "volet_roulant": "Electrique",
        "volet_battant": "Aucun",
        "moustiquaire": True,
        "frais_pose": "Standard",
        "livraison": True,
    }
    return payload


def _sale_lines(test_client: TestClient, headers: dict, sale_order_id: int) -> list:
    response = test_client.get(f"/v2/sales/{sale_order_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["lines"]


def test_mmg_configuration_persisted_and_reloaded(client):
    headers = _login(client)

    response = client.post("/v2/mmg/", json=_mmg_payload_full_options(), headers=headers)
    assert response.status_code == 200, response.text
    dossier = response.json()

    detail_resp = client.get(f"/v2/mmg/{dossier['id']}", headers=headers)
    assert detail_resp.status_code == 200, detail_resp.text
    config = detail_resp.json()["configuration"]
    assert config is not None
    assert config["shape"] == "Cintré"
    assert config["ventilation"] == "Acoustique"
    assert config["soubassement_type"] == "Plein"
    assert config["annexes"]["volet_roulant"] == "Electrique"
    assert config["annexes"]["moustiquaire"] is True
    assert config["annexes"]["frais_pose"] == "Standard"
    assert config["annexes"]["livraison"] is True


def test_mmg_send_quote_applies_plus_values(client):
    headers = _login(client)
    dossier = client.post("/v2/mmg/", json=_mmg_payload_full_options(), headers=headers).json()

    quote = client.post(f"/v2/mmg/{dossier['id']}/send-quote", headers=headers)
    assert quote.status_code == 200, quote.text

    detail = client.get(f"/v2/mmg/{dossier['id']}", headers=headers).json()
    lines = _sale_lines(client, headers, detail["sale_order_id"])
    by_desc = {line["description"]: line for line in lines}

    # Ligne de base : 1.2m x 1.4m = 1.68 m2 x 450 EUR/m2 (ALU) = 756.0
    base_desc = "ALU - Standard (1200.0x1400.0mm) (Pose: Neuf)"
    assert by_desc[base_desc]["unit_price"] == pytest.approx(756.0)

    # Plus-value forme cintree : 40% de 756.0 = 302.4
    assert by_desc["Plus-value Forme : Cintré"]["unit_price"] == pytest.approx(302.4)

    # Tapees d'isolation : perimetre (1.2 + 1.4) x 2 = 5.2 ml a 15 EUR/ml
    tapees = by_desc["Tapées d'isolation (100mm)"]
    assert tapees["quantity"] == pytest.approx(5.2)
    assert tapees["unit_price"] == pytest.approx(15.0)

    # Grille de ventilation acoustique : 45 EUR
    assert by_desc["Accessoire : Grille de Ventilation Acoustique"]["unit_price"] == pytest.approx(45.0)

    # Soubassement plein : 65 EUR forfaitaires
    assert by_desc["Option : Panneau de Soubassement Plein isolant"]["unit_price"] == pytest.approx(65.0)

    # Volet roulant electrique : 280 EUR
    assert by_desc["Option : Volet Roulant Electrique"]["unit_price"] == pytest.approx(280.0)

    # Prestation de pose standard : 100 EUR
    assert by_desc["Prestation : Pose Standard"]["unit_price"] == pytest.approx(100.0)

    # Moustiquaire : 85 EUR
    assert by_desc["Accessoire : Moustiquaire intégrée"]["unit_price"] == pytest.approx(85.0)

    # Livraison chantier : 50 EUR
    assert by_desc["Logistique : Frais de livraison sur chantier"]["unit_price"] == pytest.approx(50.0)


def test_mmg_send_quote_without_options_stays_retrocompatible(client):
    headers = _login(client)
    # Payload minimal historique : pas de shape/ventilation/annexes fines
    dossier = client.post("/v2/mmg/", json=_mmg_payload(), headers=headers).json()

    quote = client.post(f"/v2/mmg/{dossier['id']}/send-quote", headers=headers)
    assert quote.status_code == 200, quote.text

    detail = client.get(f"/v2/mmg/{dossier['id']}", headers=headers).json()
    lines = _sale_lines(client, headers, detail["sale_order_id"])
    descriptions = [line["description"] for line in lines]

    # Seules la ligne de base et les tapees (pose a neuf par defaut)
    assert len(lines) == 2
    assert not any("Plus-value" in desc for desc in descriptions)
    assert not any("Volet" in desc for desc in descriptions)
    assert not any("Moustiquaire" in desc for desc in descriptions)

import shutil
import sys
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
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


def _anonymized_proges_quote_pdf(
    *,
    reference: str = "PVC-TEST-001",
    second_unit_price: float = 900.0,
) -> bytes:
    first_total = 650.0
    second_total = second_unit_price
    subtotal = first_total + second_total
    buffer = BytesIO()
    document = canvas.Canvas(buffer)
    lines = [
        f"Devis N° {reference}",
        "CLIENT ANONYMISE",
        "Qté Désignation L H P.U. HT P.T. HT",
        "F01",
        "1 KOMMERLING 76 ADVANCED 1200 1400 650,00 650,00",
        "DORMANT NEUF 4 côtés",
        "Fenêtre OB 2 vantaux",
        "PF01",
        f"1 Porte fenêtre PVC 1800 2150 {second_unit_price:.2f} {second_total:.2f}".replace(".", ","),
        "DORMANT NEUF 4 côtés",
        f"MONTANT TOTAL H.T. {subtotal:.2f} €".replace(".", ","),
        "T.V.A. à 20,00 %",
        f"MONTANT TOTAL T.T.C. {subtotal * 1.2:.2f} €".replace(".", ","),
    ]
    y = 800
    for line in lines:
        document.drawString(40, y, line)
        y -= 24
    document.save()
    return buffer.getvalue()


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
        shutil.rmtree(ROOT_DIR / "uploads" / "measure_missions", ignore_errors=True)


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
    assert sites[0]["reference"].startswith("CH-")
    assert sites[0]["city"] == "Paris"
    assert sites[0]["access_instructions"] == "Portail bleu, appeler avant."

    mission = client.get(
        f"/v2/mmg/missions/{dossier['measure_mission_id']}",
        headers=headers,
    ).json()
    assert mission["status"] == "TO_REVIEW"
    assert mission["dossier_ids"] == [dossier["id"]]
    assert mission["site"]["postal_code"] == "75012"
    assert mission["site"]["reference"] == sites[0]["reference"]


def test_client_can_have_multiple_numbered_sites_and_smart_measure_defaults(client):
    headers = _login(client)
    crm_client = client.post(
        "/v2/partners/clients",
        json={
            "name": "Client Multi Chantiers",
            "phone": "0600001111",
            "address": "1 rue Facturation",
            "country": "FR",
            "customer_type": "B2B",
            "is_active": True,
        },
        headers=headers,
    ).json()

    created_sites = []
    for label, address in (
        ("Agence Centre", "10 rue du Premier Chantier"),
        ("Dépôt Nord", "20 avenue du Second Chantier"),
    ):
        response = client.post(
            "/v2/mmg/sites",
            json={
                "client_id": crm_client["id"],
                "label": label,
                "address_line1": address,
                "postal_code": "75001",
                "city": "Paris",
                "country": "FR",
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        created_sites.append(response.json())

    assert created_sites[0]["reference"].startswith("CH-")
    assert created_sites[1]["reference"].startswith("CH-")
    assert created_sites[0]["reference"] != created_sites[1]["reference"]

    site_visit = client.post(
        "/v2/mmg/missions",
        json={
            "client_id": crm_client["id"],
            "site_address_id": created_sites[1]["id"],
            "source_type": "SITE_VISIT",
            "status": "TO_SCHEDULE",
        },
        headers=headers,
    )
    assert site_visit.status_code == 200, site_visit.text
    assert site_visit.json()["project_scope"] == "SUPPLY_AND_INSTALL"
    assert site_visit.json()["site"]["reference"] == created_sites[1]["reference"]

    client_documents = client.post(
        "/v2/mmg/missions",
        json={
            "client_id": crm_client["id"],
            "site_address_id": created_sites[0]["id"],
            "source_type": "CLIENT_DOCUMENTS",
            "status": "IN_CAPTURE",
        },
        headers=headers,
    )
    assert client_documents.status_code == 200, client_documents.text
    assert client_documents.json()["project_scope"] == "SUPPLY_ONLY"


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


def test_validated_measure_mission_generates_idempotent_multi_opening_quote(client):
    headers = _login(client)
    crm_client = client.post(
        "/v2/partners/clients",
        json={
            "name": "Client Devis Multi",
            "email": "devis-multi@example.fr",
            "phone": "0600007788",
            "address": "1 rue Facturation",
            "country": "FR",
            "customer_type": "B2B",
            "is_active": True,
        },
        headers=headers,
    ).json()
    opportunity = client.post(
        "/v2/mmg/opportunities",
        json={
            "client_id": crm_client["id"],
            "owner_user_id": 1,
            "title": "Menuiseries anonymisées à chiffrer",
            "need_type": "fourniture_pose",
            "stage": "nouveau",
            "probability": 10,
        },
        headers=headers,
    )
    assert opportunity.status_code == 201, opportunity.text
    opportunity = opportunity.json()
    mission = client.post(
        "/v2/mmg/missions",
        json={
            "client_id": crm_client["id"],
            "opportunity_id": opportunity["id"],
            "site": {
                "label": "Résidence",
                "address_line1": "12 rue du Chantier",
                "postal_code": "75012",
                "city": "Paris",
                "country": "FR",
            },
            "assigned_user_id": 1,
            "scheduled_start": "2026-09-02T08:00:00",
            "scheduled_end": "2026-09-02T10:00:00",
            "purpose": "Deux menuiseries à chiffrer",
            "status": "SCHEDULED",
        },
        headers=headers,
    ).json()
    client.patch(
        f"/v2/mmg/missions/{mission['id']}/status",
        json={"status": "ON_SITE"},
        headers=headers,
    )
    opening_ids = []
    for label, width, height in (("F01", 1200, 1400), ("PF01", 1800, 2150)):
        response = client.post(
            f"/v2/mmg/missions/{mission['id']}/openings",
            json={
                "label": label,
                "room": "Séjour",
                "product_type": "WINDOW",
                "width_mm": width,
                "height_mm": height,
                "material": "ALU",
                "opening_type": "Battant",
                "sash_count": 2,
                "status": "COMPLETE",
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        opening_ids.append(response.json()["id"])

    proof = client.post(
        f"/v2/mmg/missions/{mission['id']}/documents",
        params={"opening_id": opening_ids[0], "document_type": "OPENING_PHOTO"},
        files={"file": ("tableau.jpg", b"photo-test", "image/jpeg")},
        headers=headers,
    )
    assert proof.status_code == 200, proof.text
    linked_document = proof.json()["source_documents"][0]
    assert linked_document["opening_id"] == opening_ids[0]
    assert linked_document["document_type"] == "OPENING_PHOTO"

    premature = client.post(
        f"/v2/mmg/missions/{mission['id']}/generate-quote",
        headers=headers,
    )
    assert premature.status_code == 409

    assert client.patch(
        f"/v2/mmg/missions/{mission['id']}/status",
        json={"status": "TO_REVIEW"},
        headers=headers,
    ).status_code == 200
    validated = client.patch(
        f"/v2/mmg/missions/{mission['id']}/status",
        json={"status": "VALIDATED"},
        headers=headers,
    )
    assert validated.status_code == 200, validated.text
    assert validated.json()["verification_status"] == "READY_FOR_FABRICATION"
    assert validated.json()["technical_dossier"]["quoting_status"] == "DRAFT"
    assert validated.json()["technical_dossier"]["production_status"] == "LOCKED"

    handoff = client.get(
        f"/v2/mmg/missions/{mission['id']}/technical-dossier/handoff",
        params={"target_system": "PROGES"},
        headers=headers,
    )
    assert handoff.status_code == 200, handoff.text
    assert "PROGES" in handoff.text
    assert "F01" in handoff.text
    assert "PF01" in handoff.text
    assert handoff.headers["content-disposition"].endswith('proges-transfert.csv"')

    blocked_without_technical_review = client.post(
        f"/v2/mmg/missions/{mission['id']}/generate-quote",
        headers=headers,
    )
    assert blocked_without_technical_review.status_code == 409
    assert "chiffrage" in blocked_without_technical_review.text.lower()

    technical_version = client.post(
        f"/v2/mmg/missions/{mission['id']}/technical-dossier/versions",
        data={
            "document_type": "QUOTING",
            "source_system": "AUTO",
            "source_reference": "PVC-TEST-001",
            "opening_ids": ",".join(str(value) for value in opening_ids),
            "notes": "Export technique initial",
        },
        files={
            "file": (
                "proges-anonymise.pdf",
                _anonymized_proges_quote_pdf(),
                "application/pdf",
            )
        },
        headers=headers,
    )
    assert technical_version.status_code == 200, technical_version.text
    assert technical_version.json()["versions"][0]["version_number"] == 1
    assert technical_version.json()["versions"][0]["opening_ids"] == opening_ids
    assert technical_version.json()["versions"][0]["source_system"] == "PROGES"
    assert technical_version.json()["versions"][0]["analysis_status"] == "PARSED"
    assert technical_version.json()["versions"][0]["parsed_summary"]["line_count"] == 2

    submitted = client.patch(
        f"/v2/mmg/missions/{mission['id']}/technical-dossier/submit",
        params={"phase": "QUOTING"},
        headers=headers,
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["quoting_status"] == "TO_REVIEW"

    correction = client.patch(
        f"/v2/mmg/missions/{mission['id']}/technical-dossier/review",
        json={"phase": "QUOTING", "action": "REQUEST_CORRECTION", "note": "Corriger la référence de la porte-fenêtre"},
        headers=headers,
    )
    assert correction.status_code == 200, correction.text
    assert correction.json()["quoting_status"] == "CORRECTION_REQUIRED"

    second_version = client.post(
        f"/v2/mmg/missions/{mission['id']}/technical-dossier/versions",
        data={
            "document_type": "QUOTING",
            "source_system": "AUTO",
            "source_reference": "PVC-TEST-001",
            "opening_ids": ",".join(str(value) for value in opening_ids),
            "notes": "Référence porte-fenêtre corrigée",
        },
        files={
            "file": (
                "proges-anonymise-v2.pdf",
                _anonymized_proges_quote_pdf(second_unit_price=950),
                "application/pdf",
            )
        },
        headers=headers,
    )
    assert second_version.status_code == 200, second_version.text
    assert [version["version_number"] for version in second_version.json()["versions"]] == [1, 2]
    assert second_version.json()["quoting_status"] == "DRAFT"
    assert second_version.json()["versions"][1]["comparison_summary"]["has_changes"] is True
    assert second_version.json()["versions"][1]["comparison_summary"]["changed_count"] == 1

    resubmitted = client.patch(
        f"/v2/mmg/missions/{mission['id']}/technical-dossier/submit",
        params={"phase": "QUOTING"},
        headers=headers,
    )
    assert resubmitted.status_code == 200, resubmitted.text

    technical_validation = client.patch(
        f"/v2/mmg/missions/{mission['id']}/technical-dossier/review",
        json={"phase": "QUOTING", "action": "VALIDATE", "note": "Cohérent avec les ouvrages du métré"},
        headers=headers,
    )
    assert technical_validation.status_code == 200, technical_validation.text
    assert technical_validation.json()["quoting_status"] == "VALIDATED"

    generated = client.post(
        f"/v2/mmg/missions/{mission['id']}/generate-quote",
        headers=headers,
    )
    assert generated.status_code == 200, generated.text
    result = generated.json()
    assert result["created"] is True
    assert result["line_count"] == 2

    fabrication_before_signature = client.post(
        f"/v2/mmg/missions/{mission['id']}/technical-dossier/versions",
        data={
            "document_type": "FABRICATION",
            "source_system": "PROGES",
            "opening_ids": ",".join(str(value) for value in opening_ids),
        },
        files={"file": ("fabrication.pdf", b"FABRICATION", "application/pdf")},
        headers=headers,
    )
    assert fabrication_before_signature.status_code == 409
    assert "signature" in fabrication_before_signature.text.lower()

    repeated = client.post(
        f"/v2/mmg/missions/{mission['id']}/generate-quote",
        headers=headers,
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["created"] is False
    assert repeated.json()["sale_order_id"] == result["sale_order_id"]

    sale = client.get(f"/v2/sales/{result['sale_order_id']}", headers=headers)
    assert sale.status_code == 200, sale.text
    assert sale.json()["workflow_type"] == "FABRICATION_FROM_MEASURE"
    assert sale.json()["status"] == "DRAFT"
    assert len(sale.json()["lines"]) == 2
    assert all(line["unit_price"] > 0 for line in sale.json()["lines"])
    assert sum(
        line["quantity"] * line["unit_price"] * (1 - line["discount_pct"] / 100)
        for line in sale.json()["lines"]
    ) == pytest.approx(1600)
    linked_opportunity = client.get(
        f"/v2/mmg/opportunities/{opportunity['id']}",
        headers=headers,
    )
    assert linked_opportunity.status_code == 200, linked_opportunity.text
    assert linked_opportunity.json()["sale_order_id"] == result["sale_order_id"]
    assert linked_opportunity.json()["stage"] == "proposition_a_valider"
    assert linked_opportunity.json()["estimated_amount"] == pytest.approx(1600)

    mission_detail = client.get(
        f"/v2/mmg/missions/{mission['id']}",
        headers=headers,
    ).json()
    assert mission_detail["status"] == "QUOTED"
    assert mission_detail["sale_order_id"] == result["sale_order_id"]
    linked_dossiers = [
        dossier
        for dossier in client.get("/v2/mmg/", headers=headers).json()
        if dossier["measure_mission_id"] == mission["id"]
    ]
    # La proposition commerciale ne crée aucune fiche de fabrication avant signature.
    assert linked_dossiers == []


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


def test_client_measure_documents_require_source_and_client_approval(client):
    headers = _login(client)
    crm_client = client.post(
        "/v2/partners/clients",
        json={
            "name": "Client Plans Fournis",
            "phone": "0600112233",
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
            "source_type": "CLIENT_DOCUMENTS",
            "project_scope": "SUPPLY_ONLY",
            "status": "IN_CAPTURE",
            "purpose": "Fenêtres sur plans client",
        },
        headers=headers,
    )
    assert mission_response.status_code == 200, mission_response.text
    mission = mission_response.json()
    assert mission["source_type"] == "CLIENT_DOCUMENTS"
    assert mission["verification_status"] == "UNVERIFIED"

    opening = client.post(
        f"/v2/mmg/missions/{mission['id']}/openings",
        json={
            "label": "F01",
            "width_mm": 1200,
            "height_mm": 1400,
            "status": "COMPLETE",
        },
        headers=headers,
    )
    assert opening.status_code == 200, opening.text

    no_document = client.patch(
        f"/v2/mmg/missions/{mission['id']}/status",
        json={"status": "TO_REVIEW"},
        headers=headers,
    )
    assert no_document.status_code == 422
    assert "plan ou croquis" in no_document.text

    document = client.post(
        f"/v2/mmg/missions/{mission['id']}/documents",
        files={"file": ("cotes-client.pdf", b"%PDF-1.4 client measurements", "application/pdf")},
        headers=headers,
    )
    assert document.status_code == 200, document.text
    assert document.json()["source_documents"][0]["original_filename"] == "cotes-client.pdf"

    review = client.patch(
        f"/v2/mmg/missions/{mission['id']}/status",
        json={"status": "TO_REVIEW"},
        headers=headers,
    )
    assert review.status_code == 200, review.text
    validated = client.patch(
        f"/v2/mmg/missions/{mission['id']}/status",
        json={"status": "VALIDATED"},
        headers=headers,
    )
    assert validated.status_code == 200, validated.text
    assert validated.json()["verification_status"] == "CLIENT_APPROVAL_REQUIRED"

    approval = client.patch(
        f"/v2/mmg/missions/{mission['id']}/verification",
        json={"action": "CLIENT_APPROVED"},
        headers=headers,
    )
    assert approval.status_code == 200, approval.text
    assert approval.json()["verification_status"] == "READY_FOR_FABRICATION"
    assert approval.json()["client_approved_at"] is not None


def test_agency_measure_with_install_requires_site_verification(client):
    headers = _login(client)
    crm_client = client.post(
        "/v2/partners/clients",
        json={
            "name": "Client Agence Pose",
            "phone": "0600445566",
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
            "source_type": "AGENCY_ASSISTED",
            "project_scope": "SUPPLY_AND_INSTALL",
            "site": {
                "address_line1": "8 rue du Chantier",
                "postal_code": "33000",
                "city": "Bordeaux",
                "country": "FR",
            },
            "status": "IN_CAPTURE",
        },
        headers=headers,
    ).json()
    accidental_schedule = client.put(
        f"/v2/mmg/missions/{mission['id']}",
        json={
            "assigned_user_id": 1,
            "scheduled_start": "2026-08-12T09:00:00",
            "scheduled_end": "2026-08-12T10:00:00",
        },
        headers=headers,
    )
    assert accidental_schedule.status_code == 200, accidental_schedule.text
    assert accidental_schedule.json()["status"] == "IN_CAPTURE"

    opening = client.post(
        f"/v2/mmg/missions/{mission['id']}/openings",
        json={
            "label": "PF01",
            "width_mm": 1800,
            "height_mm": 2150,
            "status": "COMPLETE",
        },
        headers=headers,
    )
    assert opening.status_code == 200, opening.text
    assert client.patch(
        f"/v2/mmg/missions/{mission['id']}/status",
        json={"status": "TO_REVIEW"},
        headers=headers,
    ).status_code == 200
    validated = client.patch(
        f"/v2/mmg/missions/{mission['id']}/status",
        json={"status": "VALIDATED"},
        headers=headers,
    )
    assert validated.status_code == 200, validated.text
    assert validated.json()["verification_status"] == "SITE_VERIFICATION_REQUIRED"

    client_approval = client.patch(
        f"/v2/mmg/missions/{mission['id']}/verification",
        json={"action": "CLIENT_APPROVED"},
        headers=headers,
    )
    assert client_approval.status_code == 200
    assert client_approval.json()["verification_status"] == "SITE_VERIFICATION_REQUIRED"

    site_verification = client.patch(
        f"/v2/mmg/missions/{mission['id']}/verification",
        json={"action": "SITE_VERIFIED"},
        headers=headers,
    )
    assert site_verification.status_code == 200, site_verification.text
    assert site_verification.json()["verification_status"] == "READY_FOR_FABRICATION"
    assert site_verification.json()["site_verified_at"] is not None


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

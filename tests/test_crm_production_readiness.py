import io

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from backend import database, models
from backend import main as backend_main
from backend.core import security
from backend.core.security import get_password_hash


def _headers(session_factory, username, permissions):
    with session_factory() as db:
        db.add(
            models.User(
                username=username,
                pin_hash=get_password_hash("4826"),
                role="SALES",
                is_active=True,
            )
        )
        db.commit()
    token = security.create_access_token(
        {
            "sub": username,
            "role": "SALES",
            "permissions": permissions,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def _client_payload(name, *, email=None, phone=None, segment=None, tags=None):
    return {
        "name": name,
        "contact_name": f"Contact {name}",
        "email": email,
        "phone": phone,
        "address": "1 rue des Clients",
        "country": "FR",
        "customer_type": "B2B",
        "segment": segment,
        "tags": tags or [],
        "is_active": True,
    }


def test_crm_read_and_write_permissions_are_enforced(isolated_client):
    client, session_factory = isolated_client
    no_access = _headers(session_factory, "crm-no-access", [])
    viewer = _headers(session_factory, "crm-viewer", ["SALES_VIEW"])
    editor = _headers(
        session_factory,
        "crm-editor",
        ["SALES_VIEW", "SALES_EDIT"],
    )

    assert client.get("/v2/partners/clients", headers=no_access).status_code == 403
    assert client.get("/v2/partners/clients", headers=viewer).status_code == 200

    denied_create = client.post(
        "/v2/partners/clients",
        json=_client_payload("Client lecture seule"),
        headers=viewer,
    )
    assert denied_create.status_code == 403

    created = client.post(
        "/v2/partners/clients",
        json=_client_payload("Client avec droits"),
        headers=editor,
    )
    assert created.status_code == 200, created.text
    client_id = created.json()["id"]

    opportunity_payload = {
        "client_id": client_id,
        "title": "Projet protégé",
        "stage": "nouveau",
        "need_type": "autre",
        "probability": 10,
    }
    denied_opportunity = client.post(
        "/v2/mmg/opportunities",
        json=opportunity_payload,
        headers=viewer,
    )
    assert denied_opportunity.status_code == 403

    allowed_opportunity = client.post(
        "/v2/mmg/opportunities",
        json=opportunity_payload,
        headers=editor,
    )
    assert allowed_opportunity.status_code == 201, allowed_opportunity.text


def test_multiple_contacts_keep_one_primary_and_sync_legacy_fields(isolated_client):
    client, session_factory = isolated_client
    headers = _headers(
        session_factory,
        "crm-contact-editor",
        ["SALES_VIEW", "SALES_EDIT"],
    )
    created = client.post(
        "/v2/partners/clients",
        json=_client_payload(
            "Client Multi Contact",
            email="direction@example.test",
            phone="0102030405",
        ),
        headers=headers,
    ).json()
    client_id = created["id"]

    first_contacts = client.get(
        f"/v2/partners/clients/{client_id}/contacts",
        headers=headers,
    )
    assert first_contacts.status_code == 200
    assert len(first_contacts.json()) == 1
    assert first_contacts.json()[0]["is_primary"] is True

    added = client.post(
        f"/v2/partners/clients/{client_id}/contacts",
        json={
            "name": "Mme Achats",
            "role": "Décisionnaire achats",
            "email": "achats@example.test",
            "phone": "0607080910",
            "is_primary": True,
        },
        headers=headers,
    )
    assert added.status_code == 200, added.text

    contacts = client.get(
        f"/v2/partners/clients/{client_id}/contacts",
        headers=headers,
    ).json()
    assert len(contacts) == 2
    assert sum(contact["is_primary"] for contact in contacts) == 1
    assert next(contact for contact in contacts if contact["is_primary"])["name"] == "Mme Achats"

    refreshed = client.get("/v2/partners/clients", headers=headers).json()
    record = next(item for item in refreshed if item["id"] == client_id)
    assert record["contact_name"] == "Mme Achats"
    assert record["email"] == "achats@example.test"
    assert record["phone"] == "0607080910"


def test_duplicate_detection_merge_and_segmentation(isolated_client):
    client, session_factory = isolated_client
    headers = _headers(
        session_factory,
        "crm-merge-editor",
        ["SALES_VIEW", "SALES_EDIT"],
    )
    target = client.post(
        "/v2/partners/clients",
        json=_client_payload(
            "Entreprise Exemple",
            email="contact@example.test",
            segment="Grands comptes",
            tags=["Prioritaire"],
        ),
        headers=headers,
    ).json()
    source = client.post(
        "/v2/partners/clients",
        json=_client_payload(
            "Entreprise Exemple SAS",
            email="CONTACT@example.test",
            tags=["Prescription"],
        ),
        headers=headers,
    ).json()

    with session_factory() as db:
        db.add(
            models.CRMActivity(
                client_id=source["id"],
                activity_type=models.CRMActivityType.NOTE.value,
                subject="Historique à conserver",
                status=models.CRMActivityStatus.COMPLETED.value,
                author="test",
            )
        )
        db.commit()

    candidates = client.get(
        f"/v2/partners/clients/{target['id']}/duplicates",
        headers=headers,
    )
    assert candidates.status_code == 200
    assert candidates.json()[0]["client"]["id"] == source["id"]
    assert "Même email" in candidates.json()[0]["reasons"]

    merged = client.post(
        f"/v2/partners/clients/{target['id']}/merge",
        json={"source_client_ids": [source["id"]], "confirm": True},
        headers=headers,
    )
    assert merged.status_code == 200, merged.text
    assert merged.json()["merged_client_ids"] == [source["id"]]
    assert set(merged.json()["target"]["tags"]) == {"Prioritaire", "Prescription"}

    with session_factory() as db:
        assert db.get(models.Client, source["id"]) is None
        subjects = {
            row.subject
            for row in db.query(models.CRMActivity)
            .filter(models.CRMActivity.client_id == target["id"])
            .all()
        }
    assert {"Historique à conserver", "Fiches clients fusionnées"}.issubset(subjects)


def test_client_csv_import_export_and_filters(isolated_client):
    client, session_factory = isolated_client
    headers = _headers(
        session_factory,
        "crm-import-editor",
        ["SALES_VIEW", "SALES_EDIT"],
    )
    csv_content = (
        "name,contact_name,email,phone,address,country,tax_id,customer_type,"
        "segment,tags,is_active\n"
        "Client CSV,Mme CSV,csv@example.test,0600000000,2 rue CSV,FR,,B2B,"
        "Architectes,Prescription;Actif,true\n"
    )
    imported = client.post(
        "/v2/partners/clients/import",
        files={"file": ("clients.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        headers=headers,
    )
    assert imported.status_code == 200, imported.text
    assert imported.json() == {
        "created": 1,
        "updated": 0,
        "skipped": 0,
        "errors": [],
    }

    filtered = client.get(
        "/v2/partners/clients",
        params={"segment": "Architectes", "tag": "Prescription"},
        headers=headers,
    )
    assert filtered.status_code == 200
    assert [item["name"] for item in filtered.json()] == ["Client CSV"]

    exported = client.get("/v2/partners/clients/export.csv", headers=headers)
    assert exported.status_code == 200
    assert "attachment; filename=\"clients-crm.csv\"" == exported.headers["content-disposition"]
    assert "Client CSV" in exported.content.decode("utf-8-sig")


def test_autonomous_reminder_sync_uses_application_session(isolated_client):
    _, session_factory = isolated_client
    with session_factory() as db:
        client = models.Client(name="Client Scheduler")
        db.add(client)
        db.flush()
        db.add(
            models.CRMOpportunity(
                reference="OPP-SCHEDULER-001",
                client_id=client.id,
                title="Projet à relancer",
                stage=models.CRMOpportunityStage.NEW.value,
                probability=10,
                created_by="test",
            )
        )
        db.commit()

    result = backend_main._sync_crm_reminders_once()
    assert result["created"] == 1
    with session_factory() as db:
        assert db.query(models.CRMReminderPlan).count() == 1


def test_production_requires_smtp_when_crm_reminders_are_enabled(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CRM_REMINDERS_ENABLED", "true")
    monkeypatch.setenv("CRM_SMTP_REQUIRED", "true")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_FROM", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)

    with pytest.raises(RuntimeError, match="SMTP_HOST"):
        backend_main._validate_crm_email_configuration()

    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_FROM", "crm@example.test")
    backend_main._validate_crm_email_configuration()


def test_crm_client_migration_backfills_primary_contact(tmp_path):
    db_path = tmp_path / "crm-client-upgrade.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE clients (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR UNIQUE,
                    contact_name VARCHAR,
                    email VARCHAR,
                    phone VARCHAR,
                    address VARCHAR,
                    country VARCHAR,
                    tax_id VARCHAR,
                    customer_type VARCHAR,
                    is_active BOOLEAN,
                    created_at DATETIME
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO clients (
                    id, name, contact_name, email, phone, is_active, created_at
                ) VALUES (
                    1, 'Client historique', 'Mme Historique',
                    'historique@example.test', '0101010101', 1,
                    '2026-07-01 09:00:00'
                )
                """
            )
        )

    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.stamp(config, "e9c5a2d7f104")
    command.upgrade(config, "f0a1b2c3d4e5")

    client_columns = {
        column["name"] for column in inspect(engine).get_columns("clients")
    }
    assert {"segment", "tags"}.issubset(client_columns)
    with engine.connect() as connection:
        contact = connection.execute(
            text(
                "SELECT name, email, phone, is_primary "
                "FROM client_contacts WHERE client_id = 1"
            )
        ).one()
    assert contact == (
        "Mme Historique",
        "historique@example.test",
        "0101010101",
        1,
    )

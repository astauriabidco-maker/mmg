import io
from datetime import timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from backend import database, models
from backend import main as backend_main
from backend.core import security
from backend.core.security import get_password_hash
from backend.core.time import utcnow


def _headers(session_factory, username, permissions, role="SALES"):
    with session_factory() as db:
        db.add(
            models.User(
                username=username,
                pin_hash=get_password_hash("4826"),
                role=role,
                is_active=True,
            )
        )
        db.commit()
    token = security.create_access_token(
        {
            "sub": username,
            "role": role,
            "roles": [role],
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


def test_legacy_presales_mutations_require_sales_edit(isolated_client):
    client, session_factory = isolated_client
    viewer = _headers(session_factory, "legacy-crm-viewer", ["SALES_VIEW"])

    checks = [
        ("post", "/v2/sales/stages", [{"id": "draft", "title": "Brouillon"}], None),
        ("put", "/v2/sales/999/status?status=SENT", None, None),
        ("post", "/v2/sales/999/deliver-free-sale", None, None),
        ("post", "/v2/sales/999/return-free-sale", None, None),
        ("post", "/v2/sales/999/launch-production", None, None),
        ("post", "/v2/mmg/from-sale/999", None, None),
        ("post", "/v2/mmg/999/send-quote", None, None),
        ("post", "/v2/mmg/missions/999/technical-dossier/reservation", None, None),
    ]
    for method, url, json_payload, data_payload in checks:
        response = getattr(client, method)(
            url,
            headers=viewer,
            json=json_payload,
            data=data_payload,
        )
        assert response.status_code == 403, f"{method.upper()} {url}: {response.text}"


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


def test_enriched_client_contact_fields_are_persisted_and_updatable(isolated_client):
    client, session_factory = isolated_client
    headers = _headers(
        session_factory,
        "crm-enriched-contact-editor",
        ["SALES_VIEW", "SALES_EDIT"],
    )
    created = client.post(
        "/v2/partners/clients",
        json=_client_payload(
            "Client Contact Enrichi",
            email="legacy@example.test",
            phone="0101010101",
        ),
        headers=headers,
    ).json()
    client_id = created["id"]

    added = client.post(
        f"/v2/partners/clients/{client_id}/contacts",
        json={
            "name": "Mme Prescription",
            "role": "Architecte",
            "priority": 1,
            "influence_role": "prescriber",
            "preferred_channel": "email",
            "email_consent": True,
            "email_consent_at": "2026-09-02T12:00:00Z",
            "email": "prescription@example.test",
            "phone": "0600000001",
            "is_primary": True,
            "notes": "Décide des prescriptions techniques.",
        },
        headers=headers,
    )
    assert added.status_code == 200, added.text
    payload = added.json()
    assert payload["priority"] == 1
    assert payload["influence_role"] == "PRESCRIBER"
    assert payload["preferred_channel"] == "EMAIL"
    assert payload["email_consent"] is True
    assert payload["email_consent_at"].startswith("2026-09-02T12:00:00")

    updated = client.patch(
        f"/v2/partners/clients/{client_id}/contacts/{payload['id']}",
        json={
            "priority": 2,
            "influence_role": "decision_maker",
            "preferred_channel": "phone",
            "email_consent": False,
        },
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    updated_payload = updated.json()
    assert updated_payload["priority"] == 2
    assert updated_payload["influence_role"] == "DECISION_MAKER"
    assert updated_payload["preferred_channel"] == "PHONE"
    assert updated_payload["email_consent"] is False
    assert updated_payload["email_consent_at"] is None

    invalid = client.patch(
        f"/v2/partners/clients/{client_id}/contacts/{payload['id']}",
        json={"preferred_channel": "fax"},
        headers=headers,
    )
    assert invalid.status_code == 422

    refreshed = client.get("/v2/partners/clients", headers=headers).json()
    record = next(item for item in refreshed if item["id"] == client_id)
    assert record["contact_name"] == "Mme Prescription"
    assert record["email"] == "prescription@example.test"


def test_contact_duplicate_detection_flags_same_person_inside_client(isolated_client):
    client, session_factory = isolated_client
    headers = _headers(
        session_factory,
        "crm-contact-duplicate-editor",
        ["SALES_VIEW", "SALES_EDIT"],
    )
    created = client.post(
        "/v2/partners/clients",
        json=_client_payload("Client Contacts Doublons"),
        headers=headers,
    )
    assert created.status_code == 200, created.text
    client_id = created.json()["id"]

    first = client.post(
        f"/v2/partners/clients/{client_id}/contacts",
        json={
            "name": "Mme Décision",
            "role": "Direction",
            "email": "decision@example.test",
            "phone": "06 01 02 03 04",
            "priority": 1,
            "influence_role": "DECISION_MAKER",
            "preferred_channel": "EMAIL",
            "email_consent": True,
        },
        headers=headers,
    )
    assert first.status_code == 200, first.text
    second = client.post(
        f"/v2/partners/clients/{client_id}/contacts",
        json={
            "name": "Mme Decision",
            "role": "Direction",
            "email": "DECISION@example.test",
            "phone": "+33 6 01 02 03 04",
            "priority": 2,
            "influence_role": "BUYER",
            "preferred_channel": "PHONE",
        },
        headers=headers,
    )
    assert second.status_code == 200, second.text

    duplicates = client.get(
        f"/v2/partners/clients/{client_id}/contacts/duplicates",
        headers=headers,
    )
    assert duplicates.status_code == 200, duplicates.text
    payload = duplicates.json()
    assert len(payload) == 1
    assert payload[0]["score"] == 100
    assert {"Même email contact", "Même téléphone contact"}.issubset(
        set(payload[0]["reasons"])
    )
    assert {contact["id"] for contact in payload[0]["contacts"]} == {
        first.json()["id"],
        second.json()["id"],
    }


def test_recipe_fixture_client_cleanup_is_admin_only_and_guarded(isolated_client):
    client, session_factory = isolated_client
    editor_headers = _headers(
        session_factory,
        "crm-cleanup-editor",
        ["SALES_VIEW", "SALES_EDIT"],
    )
    admin_headers = _headers(
        session_factory,
        "crm-cleanup-admin",
        ["*"],
        role="ADMIN",
    )
    recipe = client.post(
        "/v2/partners/clients",
        json=_client_payload(
            "RECETTE DOUBLON CRM CLEANUP",
            email="cleanup-recette@example.test",
            segment="Recette CRM",
            tags=["Doublon", "Recette"],
        ),
        headers=admin_headers,
    )
    assert recipe.status_code == 200, recipe.text
    normal = client.post(
        "/v2/partners/clients",
        json=_client_payload("Client Réel Non Fixture"),
        headers=admin_headers,
    )
    assert normal.status_code == 200, normal.text

    denied_role = client.delete(
        f"/v2/partners/clients/{recipe.json()['id']}/recipe-fixture",
        headers=editor_headers,
    )
    assert denied_role.status_code == 403

    denied_guard = client.delete(
        f"/v2/partners/clients/{normal.json()['id']}/recipe-fixture",
        headers=admin_headers,
    )
    assert denied_guard.status_code == 422

    deleted = client.delete(
        f"/v2/partners/clients/{recipe.json()['id']}/recipe-fixture",
        headers=admin_headers,
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted_name"] == "RECETTE DOUBLON CRM CLEANUP"

    clients = client.get("/v2/partners/clients", headers=admin_headers)
    assert clients.status_code == 200
    names = {item["name"] for item in clients.json()}
    assert "RECETTE DOUBLON CRM CLEANUP" not in names
    assert "Client Réel Non Fixture" in names


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


def test_autonomous_reminder_worker_dispatches_due_email(isolated_client, monkeypatch):
    _, session_factory = isolated_client
    monkeypatch.setattr(
        "backend.services.crm_reminders._send_smtp_email",
        lambda recipient, subject, text_body, html_body: True,
    )
    entered_at = utcnow() - timedelta(days=5)
    with session_factory() as db:
        client = models.Client(
            name="Client Relance Auto",
            contact_name="Direction",
            email="auto@example.test",
        )
        db.add(client)
        db.flush()
        db.add(
            models.CRMOpportunity(
                reference="OPP-AUTO-001",
                client_id=client.id,
                title="Projet relance automatique",
                stage=models.CRMOpportunityStage.PROPOSAL_SENT.value,
                stage_entered_at=entered_at,
                created_at=entered_at,
                probability=50,
                created_by="test",
            )
        )
        db.commit()

    result = backend_main._sync_crm_reminders_once()

    assert result["created"] == 1
    assert result["processed"] == 1
    assert result["sent"] == 1
    with session_factory() as db:
        plan = db.query(models.CRMReminderPlan).one()
        delivery = db.query(models.CRMReminderDelivery).one()
        activity = db.query(models.CRMActivity).one()
        assert plan.status == "SENT"
        assert plan.sent_delivery_id == delivery.id
        assert delivery.status == "SENT"
        assert delivery.activity_id == activity.id
        assert activity.activity_type == models.CRMActivityType.EMAIL.value


def test_autonomous_reminder_worker_skips_once_without_smtp(isolated_client, monkeypatch):
    _, session_factory = isolated_client
    monkeypatch.setattr(
        "backend.services.crm_reminders._send_smtp_email",
        lambda recipient, subject, text_body, html_body: False,
    )
    entered_at = utcnow() - timedelta(days=5)
    with session_factory() as db:
        client = models.Client(
            name="Client Sans SMTP",
            contact_name="Direction",
            email="skip@example.test",
        )
        db.add(client)
        db.flush()
        db.add(
            models.CRMOpportunity(
                reference="OPP-SKIP-001",
                client_id=client.id,
                title="Projet relance sans SMTP",
                stage=models.CRMOpportunityStage.PROPOSAL_SENT.value,
                stage_entered_at=entered_at,
                created_at=entered_at,
                probability=50,
                created_by="test",
            )
        )
        db.commit()

    first_result = backend_main._sync_crm_reminders_once()
    second_result = backend_main._sync_crm_reminders_once()

    assert first_result["processed"] == 1
    assert first_result["skipped"] == 1
    assert second_result["created"] == 0
    assert second_result["processed"] == 0
    with session_factory() as db:
        plan = db.query(models.CRMReminderPlan).one()
        delivery = db.query(models.CRMReminderDelivery).one()
        assert plan.status == "SKIPPED"
        assert plan.sent_delivery_id == delivery.id
        assert delivery.status == "SKIPPED"
        assert "SMTP non configuré" in delivery.error_message


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


def test_crm_contact_enrichment_migration_keeps_existing_contacts(tmp_path):
    db_path = tmp_path / "crm-contact-enrichment.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE client_contacts (
                    id INTEGER PRIMARY KEY,
                    client_id INTEGER NOT NULL,
                    name VARCHAR NOT NULL,
                    role VARCHAR,
                    email VARCHAR,
                    phone VARCHAR,
                    is_primary BOOLEAN NOT NULL,
                    notes TEXT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO client_contacts (
                    id, client_id, name, role, email, phone, is_primary,
                    created_at, updated_at
                ) VALUES (
                    1, 1, 'Mme Historique', 'Contact principal',
                    'historique@example.test', '0101010101', 1,
                    '2026-07-01 09:00:00', '2026-07-01 09:00:00'
                )
                """
            )
        )

    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.stamp(config, "a2c4e6f8b103")
    command.upgrade(config, "a3d9f2c8b601")

    contact_columns = {
        column["name"] for column in inspect(engine).get_columns("client_contacts")
    }
    assert {
        "priority",
        "influence_role",
        "preferred_channel",
        "email_consent",
        "email_consent_at",
    }.issubset(contact_columns)
    with engine.connect() as connection:
        contact = connection.execute(
            text(
                "SELECT priority, influence_role, preferred_channel, email_consent, email_consent_at "
                "FROM client_contacts WHERE id = 1"
            )
        ).one()
    assert contact == (3, None, None, 0, None)

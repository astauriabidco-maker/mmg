"""Contract tests for the CRM opportunity and activity API.

These tests intentionally describe the public API before its backend
implementation. They must stay independent from frontend details.

Expected endpoints:

* ``/v2/mmg/opportunities``
* ``/v2/mmg/opportunities/{opportunity_id}``
* ``/v2/mmg/crm/cockpit/opportunities/{opportunity_id}/assign-owner``
* ``/v2/mmg/crm/cockpit/opportunities/{opportunity_id}/schedule-action``
* ``/v2/mmg/activities``
* ``/v2/mmg/activities/{activity_id}``

The stage vocabulary follows the MMG pre-sales workflow, including measure
planning and proposal preparation.
"""

import pytest

from backend import models
from backend.core import security
from backend.core.security import get_password_hash


OPPORTUNITY_STAGES = (
    "nouveau",
    "qualifie",
    "metre_a_planifier",
    "metre_en_cours",
    "proposition_a_preparer",
    "proposition_a_valider",
    "proposition_envoyee",
    "negociation",
    "gagne",
    "perdu",
)


@pytest.fixture()
def crm_api(isolated_client):
    client, session_factory = isolated_client
    with session_factory() as db:
        user = models.User(
            username="crm-contract-admin",
            pin_hash=get_password_hash("4837"),
            role="ADMIN",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id

    token = security.create_access_token(
        {"sub": "crm-contract-admin", "role": "ADMIN"}
    )
    headers = {"Authorization": f"Bearer {token}"}
    return client, headers, user_id


def _create_client(client, headers, name):
    response = client.post(
        "/v2/partners/clients",
        json={
            "name": name,
            "contact_name": "Mme Client",
            "email": "crm-contract@example.fr",
            "phone": "0601020304",
            "address": "1 rue de la Facturation",
            "country": "FR",
            "customer_type": "B2B",
            "is_active": True,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_site(client, headers, client_id, label="Chantier principal"):
    response = client.post(
        "/v2/mmg/sites",
        json={
            "client_id": client_id,
            "label": label,
            "address_line1": "15 avenue du Chantier",
            "postal_code": "69003",
            "city": "Lyon",
            "country": "FR",
            "contact_name": "M. Chantier",
            "contact_phone": "0605060708",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _opportunity_payload(client_id, site_id, owner_user_id, **overrides):
    payload = {
        "client_id": client_id,
        "site_address_id": site_id,
        "title": "Remplacement des menuiseries du siège",
        "stage": "nouveau",
        "owner_user_id": owner_user_id,
        "need_type": "fourniture_pose",
        "estimated_amount": 18000.0,
        "probability": 20,
        "next_milestone": "Qualifier le besoin avec le client",
        "next_milestone_at": "2026-08-03T09:00:00Z",
    }
    payload.update(overrides)
    return payload


def _create_opportunity(client, headers, payload):
    response = client.post(
        "/v2/mmg/opportunities",
        json=payload,
        headers=headers,
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def _activity_payload(client_id, opportunity_id, **overrides):
    payload = {
        "client_id": client_id,
        "opportunity_id": opportunity_id,
        "activity_type": "appel",
        "subject": "Appeler le client pour confirmer le rendez-vous",
        "due_at": "2026-08-02T14:00:00Z",
        "status": "a_faire",
        "note": "Valider les interlocuteurs et l'accès au chantier.",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "path",
    (
        "/v2/mmg/opportunities",
        "/v2/mmg/activities",
    ),
)
def test_crm_lists_require_authentication(isolated_client, path):
    client, _ = isolated_client

    response = client.get(path)

    assert response.status_code == 401, response.text


def test_opportunity_crud_list_and_client_filter(crm_api):
    client, headers, user_id = crm_api
    first_client = _create_client(client, headers, "Client Opportunité Alpha")
    second_client = _create_client(client, headers, "Client Opportunité Beta")
    first_site = _create_site(client, headers, first_client["id"])

    opportunity = _create_opportunity(
        client,
        headers,
        _opportunity_payload(first_client["id"], first_site["id"], user_id),
    )
    second_opportunity = _create_opportunity(
        client,
        headers,
        _opportunity_payload(
            second_client["id"],
            None,
            user_id,
            title="Projet secondaire sans chantier défini",
        ),
    )

    assert opportunity["client_id"] == first_client["id"]
    assert opportunity["site_address_id"] == first_site["id"]
    assert opportunity["stage"] == "nouveau"
    assert opportunity["next_milestone"] == "Qualifier le besoin avec le client"
    assert opportunity["id"] is not None

    detail = client.get(
        f"/v2/mmg/opportunities/{opportunity['id']}",
        headers=headers,
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["title"] == opportunity["title"]

    filtered = client.get(
        "/v2/mmg/opportunities",
        params={"client_id": first_client["id"]},
        headers=headers,
    )
    assert filtered.status_code == 200, filtered.text
    assert [item["id"] for item in filtered.json()] == [opportunity["id"]]

    updated = client.post(
        f"/v2/mmg/opportunities/{opportunity['id']}/qualify",
        json={
            "need_type": "fourniture_seule",
            "study_route": "DIRECT_QUOTE",
            "project_scope": "SUPPLY_ONLY",
            "estimated_amount": 18000,
            "expected_close_date": "2026-08-05T08:00:00Z",
            "qualification_note": "Besoin confirmé pour une fourniture catalogue.",
        },
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["opportunity"]["stage"] == "qualifie"
    assert updated.json()["opportunity"]["probability"] == 30
    assert updated.json()["mission_id"] is None
    assert updated.json()["study_route"] == "DIRECT_QUOTE"

    deleted = client.delete(
        f"/v2/mmg/opportunities/{second_opportunity['id']}",
        headers=headers,
    )
    assert deleted.status_code == 204, deleted.text
    missing = client.get(
        f"/v2/mmg/opportunities/{second_opportunity['id']}",
        headers=headers,
    )
    assert missing.status_code == 404, missing.text


def test_opportunity_rejects_site_owned_by_another_client(crm_api):
    client, headers, user_id = crm_api
    first_client = _create_client(client, headers, "Client Cohérence Alpha")
    second_client = _create_client(client, headers, "Client Cohérence Beta")
    second_site = _create_site(client, headers, second_client["id"], "Site Beta")

    response = client.post(
        "/v2/mmg/opportunities",
        json=_opportunity_payload(
            first_client["id"],
            second_site["id"],
            user_id,
        ),
        headers=headers,
    )

    assert response.status_code == 400, response.text
    assert "client" in response.text.lower()
    assert "chantier" in response.text.lower() or "site" in response.text.lower()


def test_qualification_creates_site_measure_mission_and_drives_pipeline(
    crm_api,
    isolated_client,
):
    client, headers, user_id = crm_api
    _, session_factory = isolated_client
    crm_client = _create_client(client, headers, "Client Qualification Métré")
    site = _create_site(client, headers, crm_client["id"], "Chantier Lyon")
    opportunity = _create_opportunity(
        client,
        headers,
        _opportunity_payload(crm_client["id"], site["id"], user_id),
    )

    qualified = client.post(
        f"/v2/mmg/opportunities/{opportunity['id']}/qualify",
        json={
            "need_type": "fourniture_pose",
            "study_route": "SITE_VISIT",
            "project_scope": "SUPPLY_AND_INSTALL",
            "site_address_id": site["id"],
            "estimated_amount": 24000,
            "qualification_note": (
                "Remplacement complet avec pose, accès chantier confirmé."
            ),
        },
        headers=headers,
    )

    assert qualified.status_code == 200, qualified.text
    result = qualified.json()
    assert result["study_route"] == "SITE_VISIT"
    assert result["mission_id"] is not None
    assert result["opportunity"]["stage"] == "metre_a_planifier"
    assert result["opportunity"]["probability"] == 40
    assert "Planifier" in result["opportunity"]["next_milestone"]

    with session_factory() as db:
        mission = db.get(models.MeasureMission, result["mission_id"])
        activity = (
            db.query(models.CRMActivity)
            .filter(
                models.CRMActivity.opportunity_id == opportunity["id"],
                models.CRMActivity.subject
                == "Qualification commerciale validée",
            )
            .one()
        )
        assert mission.client_id == crm_client["id"]
        assert mission.site_address_id == site["id"]
        assert mission.opportunity_id == opportunity["id"]
        assert mission.source_type == "SITE_VISIT"
        assert mission.project_scope == "SUPPLY_AND_INSTALL"
        assert mission.status == models.MeasureMissionStatus.TO_SCHEDULE.value
        assert activity.status == models.CRMActivityStatus.COMPLETED.value
        assert "accès chantier confirmé" in activity.note


def test_installation_qualification_requires_a_client_site(crm_api):
    client, headers, user_id = crm_api
    crm_client = _create_client(client, headers, "Client Sans Chantier")
    opportunity = _create_opportunity(
        client,
        headers,
        _opportunity_payload(crm_client["id"], None, user_id),
    )

    response = client.post(
        f"/v2/mmg/opportunities/{opportunity['id']}/qualify",
        json={
            "need_type": "fourniture_pose",
            "study_route": "SITE_VISIT",
            "project_scope": "SUPPLY_AND_INSTALL",
            "qualification_note": "Pose souhaitée, chantier encore à créer.",
        },
        headers=headers,
    )

    assert response.status_code == 422, response.text
    assert "adresse chantier" in response.text.lower()


def test_opportunity_rejects_unknown_stage_and_terminal_regression(crm_api):
    client, headers, user_id = crm_api
    crm_client = _create_client(client, headers, "Client Transitions")
    site = _create_site(client, headers, crm_client["id"])

    invalid_create = client.post(
        "/v2/mmg/opportunities",
        json=_opportunity_payload(
            crm_client["id"],
            site["id"],
            user_id,
            stage="etape_inconnue",
        ),
        headers=headers,
    )
    assert invalid_create.status_code == 422, invalid_create.text

    bypass_create = client.post(
        "/v2/mmg/opportunities",
        json=_opportunity_payload(
            crm_client["id"],
            site["id"],
            user_id,
            stage="qualifie",
        ),
        headers=headers,
    )
    assert bypass_create.status_code == 409, bypass_create.text
    assert "actions métier" in bypass_create.text

    opportunity = _create_opportunity(
        client,
        headers,
        _opportunity_payload(crm_client["id"], site["id"], user_id),
    )
    derived_transition = client.patch(
        f"/v2/mmg/opportunities/{opportunity['id']}",
        json={"stage": "qualifie"},
        headers=headers,
    )
    assert derived_transition.status_code == 409, derived_transition.text

    qualified = client.post(
        f"/v2/mmg/opportunities/{opportunity['id']}/qualify",
        json={
            "need_type": "fourniture_seule",
            "study_route": "DIRECT_QUOTE",
            "project_scope": "SUPPLY_ONLY",
            "qualification_note": "Vente catalogue qualifiée sans métré.",
        },
        headers=headers,
    )
    assert qualified.status_code == 200, qualified.text
    assert qualified.json()["opportunity"]["stage"] == "qualifie"

    won_without_sale = client.patch(
        f"/v2/mmg/opportunities/{opportunity['id']}",
        json={"stage": "gagne"},
        headers=headers,
    )
    assert won_without_sale.status_code == 409, won_without_sale.text

    lost = client.patch(
        f"/v2/mmg/opportunities/{opportunity['id']}",
        json={"stage": "perdu", "loss_reason": "Projet reporté"},
        headers=headers,
    )
    assert lost.status_code == 200, lost.text
    assert lost.json()["stage"] == "perdu"

    regression = client.patch(
        f"/v2/mmg/opportunities/{opportunity['id']}",
        json={"stage": "qualifie"},
        headers=headers,
    )
    assert regression.status_code == 409, regression.text


def test_opportunity_stage_changes_are_recorded_for_conversion_reporting(
    crm_api,
    isolated_client,
):
    client, headers, user_id = crm_api
    _, session_factory = isolated_client
    crm_client = _create_client(client, headers, "Client Historique Étapes")
    site = _create_site(client, headers, crm_client["id"])
    opportunity = _create_opportunity(
        client,
        headers,
        _opportunity_payload(crm_client["id"], site["id"], user_id),
    )

    transitioned = client.post(
        f"/v2/mmg/opportunities/{opportunity['id']}/qualify",
        json={
            "need_type": "fourniture_seule",
            "study_route": "DIRECT_QUOTE",
            "project_scope": "SUPPLY_ONLY",
            "qualification_note": "Besoin confirmé pour vente directe.",
        },
        headers=headers,
    )
    assert transitioned.status_code == 200, transitioned.text

    with session_factory() as db:
        events = (
            db.query(models.CRMOpportunityStageHistory)
            .filter(
                models.CRMOpportunityStageHistory.opportunity_id
                == opportunity["id"]
            )
            .order_by(models.CRMOpportunityStageHistory.changed_at.asc())
            .all()
        )

    assert [(event.from_stage, event.to_stage) for event in events] == [
        (None, "nouveau"),
        ("nouveau", "qualifie"),
    ]
    assert all(event.changed_by == "crm-contract-admin" for event in events)


def test_linked_sale_send_and_signature_drive_the_opportunity(
    crm_api,
    isolated_client,
):
    client, headers, user_id = crm_api
    _, session_factory = isolated_client
    crm_client = _create_client(client, headers, "Client Devis Raccordé")
    opportunity = _create_opportunity(
        client,
        headers,
        _opportunity_payload(
            crm_client["id"],
            None,
            user_id,
            need_type="fourniture_seule",
        ),
    )
    qualified = client.post(
        f"/v2/mmg/opportunities/{opportunity['id']}/qualify",
        json={
            "need_type": "fourniture_seule",
            "study_route": "DIRECT_QUOTE",
            "project_scope": "SUPPLY_ONLY",
            "qualification_note": "Vente directe qualifiée et chiffrée.",
        },
        headers=headers,
    )
    assert qualified.status_code == 200, qualified.text

    with session_factory() as db:
        sale = models.SaleOrder(
            reference="DEV-RACCORDE-0001",
            client_name=crm_client["name"],
            client_contact=crm_client["phone"],
            client_email=crm_client["email"],
            client_address=crm_client["address"],
            status="DRAFT",
            workflow_type="FREE_SALE",
            tax_rate=20,
            currency="EUR",
            author="crm-contract-admin",
        )
        db.add(sale)
        db.flush()
        db.add(
            models.SaleOrderLine(
                order_id=sale.id,
                line_type="SERVICE",
                description="Prestation commerciale raccordée",
                quantity=1,
                unit_price=500,
                discount_pct=0,
            )
        )
        linked_opportunity = db.get(models.CRMOpportunity, opportunity["id"])
        linked_opportunity.sale_order_id = sale.id
        db.commit()
        sale_id = sale.id

    sent = client.put(
        f"/v2/sales/{sale_id}/status",
        params={"status": "SENT"},
        headers=headers,
    )
    assert sent.status_code == 200, sent.text
    portal_link = sent.json()["portal_link"]
    assert portal_link

    after_send = client.get(
        f"/v2/mmg/opportunities/{opportunity['id']}",
        headers=headers,
    )
    assert after_send.status_code == 200, after_send.text
    assert after_send.json()["stage"] == "proposition_envoyee"
    assert after_send.json()["probability"] == 70

    with session_factory() as db:
        signature_token = db.get(models.SaleOrder, sale_id).signature_token

    signed = client.post(f"/v2/sales/portal/{signature_token}/sign")
    assert signed.status_code == 200, signed.text

    after_signature = client.get(
        f"/v2/mmg/opportunities/{opportunity['id']}",
        headers=headers,
    )
    assert after_signature.status_code == 200, after_signature.text
    assert after_signature.json()["stage"] == "gagne"
    assert after_signature.json()["probability"] == 100
    assert after_signature.json()["won_at"] is not None


def test_activity_todo_update_completion_and_filters(crm_api):
    client, headers, user_id = crm_api
    crm_client = _create_client(client, headers, "Client Activités")
    site = _create_site(client, headers, crm_client["id"])
    opportunity = _create_opportunity(
        client,
        headers,
        _opportunity_payload(crm_client["id"], site["id"], user_id),
    )

    created = client.post(
        "/v2/mmg/activities",
        json=_activity_payload(crm_client["id"], opportunity["id"]),
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    activity = created.json()
    assert activity["client_id"] == crm_client["id"]
    assert activity["opportunity_id"] == opportunity["id"]
    assert activity["status"] == "a_faire"
    assert activity["completed_at"] is None

    detail = client.get(
        f"/v2/mmg/activities/{activity['id']}",
        headers=headers,
    )
    assert detail.status_code == 200, detail.text

    filtered = client.get(
        "/v2/mmg/activities",
        params={
            "client_id": crm_client["id"],
            "opportunity_id": opportunity["id"],
            "status": "a_faire",
        },
        headers=headers,
    )
    assert filtered.status_code == 200, filtered.text
    assert [item["id"] for item in filtered.json()] == [activity["id"]]

    rescheduled = client.patch(
        f"/v2/mmg/activities/{activity['id']}",
        json={
            "subject": "Confirmer le rendez-vous de métré",
            "due_at": "2026-08-04T10:30:00Z",
        },
        headers=headers,
    )
    assert rescheduled.status_code == 200, rescheduled.text
    assert rescheduled.json()["subject"] == "Confirmer le rendez-vous de métré"

    completed = client.patch(
        f"/v2/mmg/activities/{activity['id']}",
        json={
            "status": "termine",
            "note": "Rendez-vous confirmé avec le client.",
        },
        headers=headers,
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "termine"
    assert completed.json()["completed_at"] is not None
    assert completed.json()["note"] == "Rendez-vous confirmé avec le client."

    remaining = client.get(
        "/v2/mmg/activities",
        params={"opportunity_id": opportunity["id"], "status": "a_faire"},
        headers=headers,
    )
    assert remaining.status_code == 200, remaining.text
    assert remaining.json() == []

    disposable = client.post(
        "/v2/mmg/activities",
        json=_activity_payload(
            crm_client["id"],
            opportunity["id"],
            subject="Activité créée par erreur",
        ),
        headers=headers,
    )
    assert disposable.status_code in (200, 201), disposable.text
    deleted = client.delete(
        f"/v2/mmg/activities/{disposable.json()['id']}",
        headers=headers,
    )
    assert deleted.status_code == 204, deleted.text
    missing = client.get(
        f"/v2/mmg/activities/{disposable.json()['id']}",
        headers=headers,
    )
    assert missing.status_code == 404, missing.text


def test_activity_rejects_client_opportunity_mismatch(crm_api):
    client, headers, user_id = crm_api
    opportunity_client = _create_client(
        client,
        headers,
        "Client Porteur Opportunité",
    )
    unrelated_client = _create_client(
        client,
        headers,
        "Client Activité Incohérente",
    )
    site = _create_site(client, headers, opportunity_client["id"])
    opportunity = _create_opportunity(
        client,
        headers,
        _opportunity_payload(opportunity_client["id"], site["id"], user_id),
    )

    response = client.post(
        "/v2/mmg/activities",
        json=_activity_payload(unrelated_client["id"], opportunity["id"]),
        headers=headers,
    )

    assert response.status_code == 400, response.text
    assert "client" in response.text.lower()
    assert "opportunit" in response.text.lower()


def test_cockpit_schedules_action_and_updates_opportunity_milestone(crm_api):
    client, headers, user_id = crm_api
    crm_client = _create_client(client, headers, "Client Action Cockpit")
    site = _create_site(client, headers, crm_client["id"])
    opportunity = _create_opportunity(
        client,
        headers,
        _opportunity_payload(crm_client["id"], site["id"], user_id),
    )

    response = client.post(
        f"/v2/mmg/crm/cockpit/opportunities/{opportunity['id']}/schedule-action",
        json={
            "activity_type": "appel",
            "subject": "Confirmer les contraintes d'accès",
            "note": "Appeler le conducteur de travaux avant déplacement.",
            "due_at": "2026-08-06T09:30:00Z",
        },
        headers=headers,
    )

    assert response.status_code == 201, response.text
    activity = response.json()
    assert activity["opportunity_id"] == opportunity["id"]
    assert activity["client_id"] == crm_client["id"]
    assert activity["activity_type"] == "appel"
    assert activity["status"] == "a_faire"

    updated = client.get(
        f"/v2/mmg/opportunities/{opportunity['id']}",
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["next_milestone"] == "Confirmer les contraintes d'accès"
    assert updated.json()["next_milestone_at"].startswith("2026-08-06T09:30:00")


def test_cockpit_assigns_active_owner(crm_api):
    client, headers, user_id = crm_api
    crm_client = _create_client(client, headers, "Client Affectation Cockpit")
    site = _create_site(client, headers, crm_client["id"])
    opportunity = _create_opportunity(
        client,
        headers,
        _opportunity_payload(
            crm_client["id"],
            site["id"],
            None,
        ),
    )

    response = client.post(
        f"/v2/mmg/crm/cockpit/opportunities/{opportunity['id']}/assign-owner",
        json={"owner_user_id": user_id},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["owner_user_id"] == user_id
    assert response.json()["owner_name"] == "crm-contract-admin"


def test_cockpit_rejects_scheduling_action_on_terminal_opportunity(
    crm_api,
    isolated_client,
):
    client, headers, user_id = crm_api
    _, session_factory = isolated_client
    crm_client = _create_client(client, headers, "Client Opportunité Gagnée")
    site = _create_site(client, headers, crm_client["id"])
    opportunity = _create_opportunity(
        client,
        headers,
        _opportunity_payload(
            crm_client["id"],
            site["id"],
            user_id,
        ),
    )
    with session_factory() as db:
        terminal = db.get(models.CRMOpportunity, opportunity["id"])
        terminal.stage = models.CRMOpportunityStage.WON.value
        db.commit()

    response = client.post(
        f"/v2/mmg/crm/cockpit/opportunities/{opportunity['id']}/schedule-action",
        json={
            "activity_type": "tache",
            "subject": "Action impossible",
            "due_at": "2026-08-06T09:30:00Z",
        },
        headers=headers,
    )

    assert response.status_code == 409, response.text
    assert "gagnée ou perdue" in response.text


def test_activity_rejects_reopening_completed_item(crm_api):
    client, headers, user_id = crm_api
    crm_client = _create_client(client, headers, "Client Activité Terminée")
    site = _create_site(client, headers, crm_client["id"])
    opportunity = _create_opportunity(
        client,
        headers,
        _opportunity_payload(crm_client["id"], site["id"], user_id),
    )
    activity = client.post(
        "/v2/mmg/activities",
        json=_activity_payload(crm_client["id"], opportunity["id"]),
        headers=headers,
    )
    assert activity.status_code in (200, 201), activity.text
    activity_id = activity.json()["id"]

    completed = client.patch(
        f"/v2/mmg/activities/{activity_id}",
        json={"status": "termine", "note": "Action réalisée."},
        headers=headers,
    )
    assert completed.status_code == 200, completed.text

    reopened = client.patch(
        f"/v2/mmg/activities/{activity_id}",
        json={"status": "a_faire"},
        headers=headers,
    )
    assert reopened.status_code == 409, reopened.text


def test_contract_declares_all_supported_opportunity_stages():
    """Keep the workflow vocabulary explicit for backend and future UI."""

    assert OPPORTUNITY_STAGES == (
        "nouveau",
        "qualifie",
        "metre_a_planifier",
        "metre_en_cours",
        "proposition_a_preparer",
        "proposition_a_valider",
        "proposition_envoyee",
        "negociation",
        "gagne",
        "perdu",
    )

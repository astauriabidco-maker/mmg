from datetime import datetime, timedelta

from backend import models
from backend.core.security import create_access_token


def _admin_headers(session_factory):
    db = session_factory()
    try:
        db.add(
            models.User(
                username="schedule-admin",
                pin_hash="unused",
                role="ADMIN",
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()
    token = create_access_token(
        {
            "sub": "schedule-admin",
            "role": "ADMIN",
            "roles": ["ADMIN"],
            "permissions": ["*"],
        }
    )
    return {"Authorization": f"Bearer {token}"}


def _worker_and_client(session_factory):
    db = session_factory()
    try:
        worker = models.User(
            username="metreur",
            first_name="Lina",
            last_name="Mesure",
            pin_hash="unused",
            role="SALES",
            is_active=True,
        )
        client = models.Client(name="Client Agenda", is_active=True)
        db.add_all([worker, client])
        db.commit()
        return worker.id, client.id
    finally:
        db.close()


def test_schedule_creates_lists_and_cancels_task(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    worker_id, client_id = _worker_and_client(session_factory)
    start = datetime(2026, 8, 3, 9, 0)

    response = client.post(
        "/v2/schedule/tasks",
        headers=headers,
        json={
            "title": "Préparer dossier chantier",
            "category": "ORDER",
            "start_at": start.isoformat(),
            "end_at": (start + timedelta(hours=1)).isoformat(),
            "assigned_user_id": worker_id,
            "client_id": client_id,
        },
    )
    assert response.status_code == 201, response.text
    task = response.json()
    assert task["title"] == "Préparer dossier chantier"
    assert task["owner_name"] == "Lina Mesure"
    assert task["start_at"].endswith("Z")
    assert task["end_at"].endswith("Z")

    response = client.get(
        "/v2/schedule/events",
        headers=headers,
        params={
            "start_at": datetime(2026, 8, 3).isoformat(),
            "end_at": datetime(2026, 8, 4).isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert [event["id"] for event in payload["events"]] == [task["id"]]
    assert payload["events"][0]["start_at"].endswith("Z")
    assert payload["summary"]["total"] == 1

    response = client.delete(
        f"/v2/schedule/tasks/{task['source_id']}",
        headers=headers,
    )
    assert response.status_code == 204


def test_schedule_rejects_overlapping_assignment(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    worker_id, _ = _worker_and_client(session_factory)
    start = datetime(2026, 8, 4, 14, 0)
    first = {
        "title": "Rendez-vous chantier",
        "category": "MEETING",
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(hours=2)).isoformat(),
        "assigned_user_id": worker_id,
    }
    assert client.post("/v2/schedule/tasks", headers=headers, json=first).status_code == 201

    second = {
        **first,
        "title": "Deuxième rendez-vous",
        "start_at": (start + timedelta(minutes=30)).isoformat(),
    }
    response = client.post("/v2/schedule/tasks", headers=headers, json=second)
    assert response.status_code == 409
    assert response.json()["detail"]["conflicts"]

    second["allow_conflict"] = True
    assert client.post("/v2/schedule/tasks", headers=headers, json=second).status_code == 201


def test_unscheduled_measure_mission_can_be_planned_from_calendar(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    worker_id, client_id = _worker_and_client(session_factory)
    db = session_factory()
    try:
        mission = models.MeasureMission(
            reference="MET-AGENDA-001",
            client_id=client_id,
            status=models.MeasureMissionStatus.TO_SCHEDULE.value,
            source_type="SITE_VISIT",
            project_scope="SUPPLY_AND_INSTALL",
            created_by="schedule-admin",
        )
        db.add(mission)
        db.commit()
        mission_id = mission.id
    finally:
        db.close()

    response = client.get(
        "/v2/schedule/events",
        headers=headers,
        params={
            "start_at": datetime(2026, 8, 1).isoformat(),
            "end_at": datetime(2026, 9, 1).isoformat(),
            "include_unscheduled": True,
        },
    )
    assert response.status_code == 200, response.text
    assert any(
        event["id"] == f"MEASURE_MISSION:{mission_id}"
        for event in response.json()["unscheduled"]
    )

    start = datetime(2026, 8, 10, 8, 30)
    response = client.patch(
        f"/v2/schedule/events/MEASURE_MISSION/{mission_id}",
        headers=headers,
        json={
            "start_at": start.isoformat(),
            "end_at": (start + timedelta(hours=2)).isoformat(),
            "assigned_user_id": worker_id,
        },
    )
    assert response.status_code == 200, response.text

    db = session_factory()
    try:
        mission = db.get(models.MeasureMission, mission_id)
        assert mission.status == models.MeasureMissionStatus.SCHEDULED.value
        assert mission.assigned_user_id == worker_id
        assert mission.scheduled_start == start
    finally:
        db.close()


def test_purchase_deadline_is_visible_but_read_only(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    expected = datetime(2026, 8, 12, 9, 0)
    db = session_factory()
    try:
        purchase = models.PurchaseOrder(
            reference="PO-AGENDA-001",
            supplier="CORTIZO",
            expected_date=expected,
            status=models.PurchaseOrderStatus.SENT,
            author="schedule-admin",
        )
        db.add(purchase)
        db.commit()
        purchase_id = purchase.id
    finally:
        db.close()

    response = client.get(
        "/v2/schedule/events",
        headers=headers,
        params={
            "start_at": datetime(2026, 8, 1).isoformat(),
            "end_at": datetime(2026, 9, 1).isoformat(),
        },
    )
    purchase_event = next(
        event
        for event in response.json()["events"]
        if event["id"] == f"PURCHASE:{purchase_id}"
    )
    assert purchase_event["editable"] is False

    response = client.patch(
        f"/v2/schedule/events/PURCHASE/{purchase_id}",
        headers=headers,
        json={"start_at": datetime(2026, 8, 13, 9, 0).isoformat()},
    )
    assert response.status_code == 409

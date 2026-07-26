from datetime import datetime, timedelta

from backend import models
from backend.core.security import create_access_token
from backend.services.planning_alerts import evaluate_operational_alerts


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


def _planning_view_headers(username):
    token = create_access_token(
        {
            "sub": username,
            "role": "OPERATOR",
            "roles": ["OPERATOR"],
            "permissions": ["PLANNING_VIEW"],
        }
    )
    return {"Authorization": f"Bearer {token}"}


def _create_worker(
    session_factory,
    username,
    first_name,
    last_name,
    role="SALES",
):
    db = session_factory()
    try:
        worker = models.User(
            username=username,
            first_name=first_name,
            last_name=last_name,
            pin_hash="unused",
            role=role,
            is_active=True,
        )
        db.add(worker)
        db.commit()
        return worker.id
    finally:
        db.close()


def _post_task(
    client,
    headers,
    *,
    title,
    start_at,
    end_at,
    assigned_user_id=None,
    allow_conflict=False,
):
    return client.post(
        "/v2/schedule/tasks",
        headers=headers,
        json={
            "title": title,
            "category": "TASK",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "assigned_user_id": assigned_user_id,
            "allow_conflict": allow_conflict,
        },
    )


def _add_alert_rule(
    session_factory,
    *,
    code,
    threshold_minutes=0,
    recipient_mode="RESPONSIBLE",
    severity="MEDIUM",
    escalation_minutes=30,
    notify_pwa=True,
    notify_email=True,
):
    db = session_factory()
    try:
        rule = models.PlanningAlertRule(
            code=code,
            label={
                "BLOCKED": "Tâche bloquée",
                "PAUSE_TOO_LONG": "Pause prolongée",
                "DURATION_OVERRUN": "Durée prévue dépassée",
            }[code],
            threshold_minutes=threshold_minutes,
            recipient_mode=recipient_mode,
            severity=severity,
            escalation_minutes=escalation_minutes,
            notify_pwa=notify_pwa,
            notify_email=notify_email,
            is_active=True,
        )
        db.add(rule)
        db.commit()
        return rule.id
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


def test_schedule_allows_different_workers_on_same_slot(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    first_worker_id, _ = _worker_and_client(session_factory)
    second_worker_id = _create_worker(
        session_factory,
        "poseur",
        "Nora",
        "Pose",
    )
    start = datetime(2026, 8, 5, 9, 0)
    end = start + timedelta(hours=2)

    first_response = _post_task(
        client,
        headers,
        title="Métré chantier République",
        start_at=start,
        end_at=end,
        assigned_user_id=first_worker_id,
    )
    second_response = _post_task(
        client,
        headers,
        title="Pose chantier Bastille",
        start_at=start,
        end_at=end,
        assigned_user_id=second_worker_id,
    )

    assert first_response.status_code == 201, first_response.text
    assert second_response.status_code == 201, second_response.text
    assert first_response.json()["owner_id"] == first_worker_id
    assert second_response.json()["owner_id"] == second_worker_id


def test_operator_only_receives_personal_schedule(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    first_worker_id, _ = _worker_and_client(session_factory)
    second_worker_id = _create_worker(
        session_factory,
        "poseur-personnel",
        "Nora",
        "Pose",
        role="OPERATOR",
    )
    start = datetime(2026, 8, 5, 9, 0)
    for worker_id, title in (
        (first_worker_id, "Métré confidentiel"),
        (second_worker_id, "Pose personnelle"),
    ):
        response = _post_task(
            client,
            headers,
            title=title,
            start_at=start,
            end_at=start + timedelta(hours=2),
            assigned_user_id=worker_id,
        )
        assert response.status_code == 201, response.text

    personal_headers = _planning_view_headers("poseur-personnel")
    meta = client.get("/v2/schedule/meta", headers=personal_headers)
    assert meta.status_code == 200, meta.text
    assert meta.json()["can_edit"] is False
    assert [user["id"] for user in meta.json()["users"]] == [second_worker_id]
    assert meta.json()["clients"] == []
    assert meta.json()["sale_orders"] == []

    response = client.get(
        "/v2/schedule/events",
        headers=personal_headers,
        params={
            "start_at": datetime(2026, 8, 5).isoformat(),
            "end_at": datetime(2026, 8, 6).isoformat(),
            "owner_id": first_worker_id,
        },
    )
    assert response.status_code == 200, response.text
    assert [event["title"] for event in response.json()["events"]] == [
        "Pose personnelle"
    ]


def test_schedule_meta_exposes_users_and_station_display_names(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    worker_id, _ = _worker_and_client(session_factory)
    db = session_factory()
    try:
        station = models.Station(
            code="ALU_DEBIT",
            display_name="Débit aluminium",
            order_index=2,
        )
        db.add(station)
        db.commit()
        station_id = station.id
    finally:
        db.close()

    response = client.get("/v2/schedule/meta", headers=headers)

    assert response.status_code == 200, response.text
    assert worker_id in {user["id"] for user in response.json()["users"]}
    assert response.json()["stations"] == [
        {"id": station_id, "name": "Débit aluminium"}
    ]


def test_schedule_reports_team_load_and_manager_summary(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    first_worker_id, _ = _worker_and_client(session_factory)
    second_worker_id = _create_worker(
        session_factory,
        "commercial-2",
        "Amine",
        "Vente",
    )
    day_start = datetime(2020, 1, 6, 6, 0)

    responses = [
        _post_task(
            client,
            headers,
            title="Journée métrés",
            start_at=day_start,
            end_at=day_start + timedelta(hours=8),
            assigned_user_id=first_worker_id,
        ),
        _post_task(
            client,
            headers,
            title="Urgence client",
            start_at=day_start + timedelta(hours=6),
            end_at=day_start + timedelta(hours=8),
            assigned_user_id=first_worker_id,
            allow_conflict=True,
        ),
        _post_task(
            client,
            headers,
            title="Relances commerciales",
            start_at=day_start + timedelta(hours=2),
            end_at=day_start + timedelta(hours=6),
            assigned_user_id=second_worker_id,
        ),
    ]
    assert all(response.status_code == 201 for response in responses)

    response = client.get(
        "/v2/schedule/events",
        headers=headers,
        params={
            "start_at": datetime(2020, 1, 6).isoformat(),
            "end_at": datetime(2020, 1, 7).isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    load_by_owner = {
        load["owner_id"]: load
        for load in payload["team_load"]
    }

    overloaded = load_by_owner[first_worker_id]
    assert overloaded["planned_hours"] == 10.0
    assert overloaded["capacity_hours"] == 7.0
    assert overloaded["utilization_pct"] == 142.9
    assert overloaded["overloaded"] is True
    assert overloaded["conflicts"] >= 1

    available = load_by_owner[second_worker_id]
    assert available["planned_hours"] == 4.0
    assert available["capacity_hours"] == 7.0
    assert available["utilization_pct"] == 57.1
    assert available["overloaded"] is False
    assert available["conflicts"] == 0

    summary = payload["summary"]
    assert {
        "planned_hours",
        "capacity_hours",
        "utilization_pct",
        "overloaded_users",
        "conflicts",
    } <= summary.keys()
    assert summary["planned_hours"] == sum(
        load["planned_hours"] for load in payload["team_load"]
    )
    assert summary["capacity_hours"] == sum(
        load["capacity_hours"] for load in payload["team_load"]
    )
    assert summary["utilization_pct"] == round(
        summary["planned_hours"] / summary["capacity_hours"] * 100,
        1,
    )
    assert summary["overloaded_users"] == 1
    assert summary["conflicts"] >= 1


def test_schedule_defaults_to_35_hours_per_week(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    worker_id, _ = _worker_and_client(session_factory)

    response = client.get(
        "/v2/schedule/events",
        headers=headers,
        params={
            "start_at": datetime(2026, 1, 5).isoformat(),
            "end_at": datetime(2026, 1, 12).isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    load = next(
        item
        for item in response.json()["team_load"]
        if item["owner_id"] == worker_id
    )
    assert load["contract_hours"] == 35.0
    assert load["capacity_hours"] == 35.0
    assert load["absence_hours"] == 0.0


def test_part_time_schedule_and_leave_reduce_capacity(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    worker_id, _ = _worker_and_client(session_factory)
    half_time_schedule = {
        str(weekday): [["09:00", "12:30"]]
        for weekday in range(5)
    }

    updated = client.put(
        f"/v2/schedule/availability/{worker_id}",
        headers=headers,
        json={"work_schedule": half_time_schedule},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["weekly_hours"] == 17.5

    absence = client.post(
        f"/v2/schedule/availability/{worker_id}/absences",
        headers=headers,
        json={
            "start_at": "2026-01-05T07:00:00Z",
            "end_at": "2026-01-05T12:00:00Z",
            "absence_type": "RTT",
            "reason": "Demi-journée RTT",
        },
    )
    assert absence.status_code == 201, absence.text
    assert absence.json()["status"] == "PENDING"

    review = client.patch(
        f"/v2/schedule/availability/absences/{absence.json()['id']}/review",
        headers=headers,
        json={"status": "APPROVED", "review_note": "RTT validée"},
    )
    assert review.status_code == 200, review.text
    assert review.json()["status"] == "APPROVED"

    response = client.get(
        "/v2/schedule/events",
        headers=headers,
        params={
            "start_at": datetime(2026, 1, 5).isoformat(),
            "end_at": datetime(2026, 1, 12).isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    load = next(
        item for item in payload["team_load"] if item["owner_id"] == worker_id
    )
    assert load["contract_hours"] == 17.5
    assert load["absence_hours"] == 3.5
    assert load["capacity_hours"] == 14.0
    assert any(
        event["source_type"] == "USER_ABSENCE"
        and event["owner_id"] == worker_id
        for event in payload["events"]
    )

    blocked = _post_task(
        client,
        headers,
        title="Tâche pendant RTT",
        start_at=datetime(2026, 1, 5, 8, 30),
        end_at=datetime(2026, 1, 5, 10, 0),
        assigned_user_id=worker_id,
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["conflicts"][0]["source_type"] == "USER_ABSENCE"

    forced = _post_task(
        client,
        headers,
        title="Tâche forcée pendant RTT",
        start_at=datetime(2026, 1, 5, 8, 30),
        end_at=datetime(2026, 1, 5, 10, 0),
        assigned_user_id=worker_id,
        allow_conflict=True,
    )
    assert forced.status_code == 409
    assert forced.json()["detail"]["conflicts"][0]["source_type"] == "USER_ABSENCE"


def test_schedule_exposes_actionable_manager_alerts(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    worker_id, _ = _worker_and_client(session_factory)
    day_start = datetime(2020, 2, 3, 7, 0)

    first = _post_task(
        client,
        headers,
        title="Planning complet",
        start_at=day_start,
        end_at=day_start + timedelta(hours=8),
        assigned_user_id=worker_id,
    )
    conflict = _post_task(
        client,
        headers,
        title="Intervention urgente",
        start_at=day_start + timedelta(hours=5),
        end_at=day_start + timedelta(hours=8),
        assigned_user_id=worker_id,
        allow_conflict=True,
    )
    unassigned = _post_task(
        client,
        headers,
        title="Commande à affecter",
        start_at=day_start + timedelta(hours=9),
        end_at=day_start + timedelta(hours=10),
    )
    assert first.status_code == 201
    assert conflict.status_code == 201
    assert unassigned.status_code == 201

    response = client.get(
        "/v2/schedule/events",
        headers=headers,
        params={
            "start_at": datetime(2020, 2, 3).isoformat(),
            "end_at": datetime(2020, 2, 4).isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    alerts = response.json()["alerts"]
    alert_types = {alert["type"] for alert in alerts}

    assert {"OVERLOAD", "CONFLICT", "UNASSIGNED", "OVERDUE"} <= alert_types
    assert all(alert["severity"] in {"INFO", "WARNING", "CRITICAL"} for alert in alerts)
    assert all(alert["message"] for alert in alerts)


def test_schedule_filters_events_and_load_by_owner(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    first_worker_id, _ = _worker_and_client(session_factory)
    second_worker_id = _create_worker(
        session_factory,
        "metreur-2",
        "Sara",
        "Cotes",
    )
    start = datetime(2026, 8, 6, 10, 0)

    for worker_id, title in (
        (first_worker_id, "Visite client Nord"),
        (second_worker_id, "Visite client Sud"),
        (None, "Tâche à affecter"),
    ):
        response = _post_task(
            client,
            headers,
            title=title,
            start_at=start,
            end_at=start + timedelta(hours=1),
            assigned_user_id=worker_id,
        )
        assert response.status_code == 201, response.text

    response = client.get(
        "/v2/schedule/events",
        headers=headers,
        params={
            "start_at": datetime(2026, 8, 6).isoformat(),
            "end_at": datetime(2026, 8, 7).isoformat(),
            "owner_id": first_worker_id,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert [event["title"] for event in payload["events"]] == ["Visite client Nord"]
    assert all(event["owner_id"] == first_worker_id for event in payload["events"])
    assert payload["summary"]["total"] == 1


def test_schedule_normalizes_offset_datetimes_to_utc(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    worker_id, _ = _worker_and_client(session_factory)

    response = client.post(
        "/v2/schedule/tasks",
        headers=headers,
        json={
            "title": "Rendez-vous heure de Paris",
            "category": "MEETING",
            "start_at": "2026-08-07T09:00:00+02:00",
            "end_at": "2026-08-07T10:00:00+02:00",
            "assigned_user_id": worker_id,
        },
    )
    assert response.status_code == 201, response.text
    task = response.json()
    assert task["start_at"] == "2026-08-07T07:00:00Z"
    assert task["end_at"] == "2026-08-07T08:00:00Z"

    response = client.get(
        "/v2/schedule/events",
        headers=headers,
        params={
            "start_at": "2026-08-07T00:00:00Z",
            "end_at": "2026-08-08T00:00:00Z",
        },
    )
    assert response.status_code == 200, response.text
    event = next(
        item
        for item in response.json()["events"]
        if item["source_id"] == task["source_id"]
    )
    assert event["start_at"] == "2026-08-07T07:00:00Z"
    assert event["end_at"] == "2026-08-07T08:00:00Z"


def test_schedule_executes_task_with_time_history_and_notifications(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    worker_id, _ = _worker_and_client(session_factory)
    start = datetime(2026, 8, 10, 9, 0)
    created = _post_task(
        client,
        headers,
        title="Préparer livraison client",
        start_at=start,
        end_at=start + timedelta(hours=2),
        assigned_user_id=worker_id,
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["source_id"]
    execution_url = f"/v2/schedule/events/CALENDAR_TASK/{task_id}"

    detail = client.get(f"{execution_url}/execution", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["status"] == "TODO"
    assert detail.json()["allowed_actions"] == ["START", "BLOCK"]

    started = client.post(
        f"{execution_url}/execute",
        headers=headers,
        json={"action": "START", "assigned_user_id": worker_id},
    )
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "IN_PROGRESS"

    missing_reason = client.post(
        f"{execution_url}/execute",
        headers=headers,
        json={"action": "PAUSE"},
    )
    assert missing_reason.status_code == 422

    paused = client.post(
        f"{execution_url}/execute",
        headers=headers,
        json={
            "action": "PAUSE",
            "reason": "Attente validation client",
            "time_spent_minutes": 12,
        },
    )
    assert paused.status_code == 200, paused.text
    assert paused.json()["status"] == "PAUSED"
    assert paused.json()["elapsed_minutes"] == 12

    resumed = client.post(
        f"{execution_url}/execute",
        headers=headers,
        json={"action": "START"},
    )
    assert resumed.status_code == 200, resumed.text

    completed = client.post(
        f"{execution_url}/execute",
        headers=headers,
        json={
            "action": "COMPLETE",
            "note": "Commande préparée et contrôlée",
            "time_spent_minutes": 45,
        },
    )
    assert completed.status_code == 200, completed.text
    payload = completed.json()
    assert payload["status"] == "DONE"
    assert payload["elapsed_minutes"] == 45
    assert [item["action"] for item in payload["history"]] == [
        "COMPLETE",
        "START",
        "PAUSE",
        "START",
    ]

    db = session_factory()
    try:
        task = db.get(models.CalendarTask, task_id)
        assert task.status == "DONE"
        assert (
            db.query(models.PlanningNotification)
            .filter(
                models.PlanningNotification.user_id == worker_id,
                models.PlanningNotification.source_type == "CALENDAR_TASK",
                models.PlanningNotification.source_id == task_id,
            )
            .count()
            >= 5
        )
    finally:
        db.close()


def test_blocked_task_alerts_responsible_once(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    worker_id = _create_worker(
        session_factory,
        "planning-blocked-worker",
        "Nina",
        "Atelier",
        role="OPERATOR",
    )
    _add_alert_rule(session_factory, code="BLOCKED")
    start = datetime(2026, 8, 10, 13, 0)
    created = _post_task(
        client,
        headers,
        title="Débit aluminium urgent",
        start_at=start,
        end_at=start + timedelta(hours=1),
        assigned_user_id=worker_id,
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["source_id"]
    execution_url = f"/v2/schedule/events/CALENDAR_TASK/{task_id}/execute"

    blocked = client.post(
        execution_url,
        headers=headers,
        json={
            "action": "BLOCK",
            "reason": "Profil fournisseur manquant",
        },
    )
    assert blocked.status_code == 200, blocked.text

    db = session_factory()
    try:
        alert = (
            db.query(models.PlanningNotification)
            .filter(
                models.PlanningNotification.user_id == worker_id,
                models.PlanningNotification.notification_type
                == "OPERATIONAL_BLOCKED",
            )
            .one()
        )
        assert "Débit aluminium urgent" in alert.message
        assert "Profil fournisseur manquant" in alert.message
        assert evaluate_operational_alerts(db) == 0
        db.commit()
        assert (
            db.query(models.PlanningNotification)
            .filter(
                models.PlanningNotification.user_id == worker_id,
                models.PlanningNotification.notification_type
                == "OPERATIONAL_BLOCKED",
            )
            .count()
            == 1
        )
    finally:
        db.close()


def test_pause_and_duration_alerts_respect_thresholds_and_deduplicate(
    isolated_client,
):
    _, session_factory = isolated_client
    worker_id = _create_worker(
        session_factory,
        "planning-threshold-worker",
        "Malo",
        "Pose",
        role="OPERATOR",
    )
    _add_alert_rule(
        session_factory,
        code="PAUSE_TOO_LONG",
        threshold_minutes=30,
    )
    _add_alert_rule(
        session_factory,
        code="DURATION_OVERRUN",
        threshold_minutes=15,
    )
    now = datetime(2026, 8, 11, 12, 0)

    db = session_factory()
    try:
        paused_task = models.CalendarTask(
            title="Préparer les vitrages",
            start_at=now - timedelta(hours=2),
            end_at=now - timedelta(hours=1),
            assigned_user_id=worker_id,
            created_by="test",
        )
        overrun_task = models.CalendarTask(
            title="Pose chantier République",
            start_at=now - timedelta(hours=2),
            end_at=now - timedelta(hours=1),
            assigned_user_id=worker_id,
            created_by="test",
        )
        db.add_all([paused_task, overrun_task])
        db.flush()
        paused_state = models.ScheduleExecutionState(
            source_type="CALENDAR_TASK",
            source_id=paused_task.id,
            status="PAUSED",
            assigned_user_id=worker_id,
            elapsed_minutes=20,
            updated_by_name="test",
        )
        overrun_state = models.ScheduleExecutionState(
            source_type="CALENDAR_TASK",
            source_id=overrun_task.id,
            status="IN_PROGRESS",
            assigned_user_id=worker_id,
            started_at=now - timedelta(minutes=90),
            active_since=now - timedelta(minutes=90),
            elapsed_minutes=0,
            updated_by_name="test",
        )
        db.add_all([paused_state, overrun_state])
        db.flush()
        db.add(
            models.ScheduleExecutionLog(
                state_id=paused_state.id,
                action="PAUSE",
                previous_status="IN_PROGRESS",
                current_status="PAUSED",
                reason="Pause repas",
                elapsed_minutes=20,
                responsible_user_id=worker_id,
                actor_name="test",
                created_at=now - timedelta(minutes=40),
            )
        )
        db.commit()

        assert evaluate_operational_alerts(db, now=now) == 2
        db.commit()
        alerts = (
            db.query(models.PlanningNotification)
            .filter(
                models.PlanningNotification.user_id == worker_id,
                models.PlanningNotification.notification_type.in_(
                    [
                        "OPERATIONAL_PAUSE_TOO_LONG",
                        "OPERATIONAL_DURATION_OVERRUN",
                    ]
                ),
            )
            .order_by(models.PlanningNotification.notification_type)
            .all()
        )
        assert len(alerts) == 2
        assert "40 min" in next(
            alert.message
            for alert in alerts
            if alert.notification_type == "OPERATIONAL_PAUSE_TOO_LONG"
        )
        assert "90 min" in next(
            alert.message
            for alert in alerts
            if alert.notification_type == "OPERATIONAL_DURATION_OVERRUN"
        )
        assert evaluate_operational_alerts(db, now=now) == 0
    finally:
        db.close()


def test_planning_incident_lifecycle_and_history(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    worker_id = _create_worker(
        session_factory,
        "incident-worker",
        "Nora",
        "Débit",
        role="OPERATOR",
    )
    manager_id = _create_worker(
        session_factory,
        "incident-manager",
        "Marc",
        "Atelier",
        role="ADMIN",
    )
    _add_alert_rule(
        session_factory,
        code="BLOCKED",
        severity="CRITICAL",
        escalation_minutes=15,
    )
    start = datetime(2026, 8, 12, 8, 0)
    created = _post_task(
        client,
        headers,
        title="Découpe profils chantier",
        start_at=start,
        end_at=start + timedelta(hours=1),
        assigned_user_id=worker_id,
    )
    task_id = created.json()["source_id"]
    execution_url = f"/v2/schedule/events/CALENDAR_TASK/{task_id}/execute"
    blocked = client.post(
        execution_url,
        headers=headers,
        json={"action": "BLOCK", "reason": "Matière non disponible"},
    )
    assert blocked.status_code == 200, blocked.text

    response = client.get(
        "/v2/schedule/incidents",
        headers=headers,
        params={"incident_status": "OPEN"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["summary"]["open"] == 1
    incident = response.json()["incidents"][0]
    assert incident["severity"] == "CRITICAL"
    assert incident["responsible_user_id"] == worker_id

    acknowledged = client.post(
        f"/v2/schedule/incidents/{incident['id']}/acknowledge",
        headers=headers,
        json={
            "comment": "Prise en charge par le chef d’atelier",
            "assigned_manager_user_id": manager_id,
        },
    )
    assert acknowledged.status_code == 200, acknowledged.text
    assert acknowledged.json()["status"] == "ACKNOWLEDGED"
    assert acknowledged.json()["assigned_manager_user_id"] == manager_id

    commented = client.post(
        f"/v2/schedule/incidents/{incident['id']}/comments",
        headers=headers,
        json={"comment": "Approvisionnement de secours identifié"},
    )
    assert commented.status_code == 200, commented.text

    resolved = client.post(
        f"/v2/schedule/incidents/{incident['id']}/resolve",
        headers=headers,
        json={"comment": "Profil livré au poste de débit"},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "RESOLVED"
    actions = [entry["action"] for entry in resolved.json()["history"]]
    assert actions == ["CREATED", "ACKNOWLEDGED", "COMMENTED", "RESOLVED"]


def test_planning_incident_auto_resolves_when_task_restarts(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    worker_id = _create_worker(
        session_factory,
        "incident-resume-worker",
        "Lina",
        "PVC",
        role="OPERATOR",
    )
    _add_alert_rule(session_factory, code="BLOCKED")
    start = datetime(2026, 8, 13, 8, 0)
    created = _post_task(
        client,
        headers,
        title="Débit PVC",
        start_at=start,
        end_at=start + timedelta(hours=1),
        assigned_user_id=worker_id,
    )
    task_id = created.json()["source_id"]
    execution_url = f"/v2/schedule/events/CALENDAR_TASK/{task_id}/execute"
    assert client.post(
        execution_url,
        headers=headers,
        json={"action": "BLOCK", "reason": "Machine en réglage"},
    ).status_code == 200
    assert client.post(
        execution_url,
        headers=headers,
        json={"action": "START"},
    ).status_code == 200

    response = client.get(
        "/v2/schedule/incidents",
        headers=headers,
        params={"incident_status": "RESOLVED"},
    )
    assert response.status_code == 200, response.text
    incident = response.json()["incidents"][0]
    detail = client.get(
        f"/v2/schedule/incidents/{incident['id']}",
        headers=headers,
    )
    assert detail.json()["status"] == "RESOLVED"
    assert detail.json()["history"][-1]["action"] == "AUTO_RESOLVED"


def test_planning_incident_reassignment_updates_source_and_notifies(
    isolated_client,
):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    first_worker_id = _create_worker(
        session_factory,
        "incident-first-worker",
        "Nora",
        "PVC",
        role="OPERATOR",
    )
    second_worker_id = _create_worker(
        session_factory,
        "incident-second-worker",
        "Mila",
        "ALU",
        role="OPERATOR",
    )
    _add_alert_rule(session_factory, code="BLOCKED")
    start = datetime(2026, 8, 13, 10, 0)
    created = _post_task(
        client,
        headers,
        title="Débit atelier à réaffecter",
        start_at=start,
        end_at=start + timedelta(hours=1),
        assigned_user_id=first_worker_id,
    )
    task_id = created.json()["source_id"]
    assert client.post(
        f"/v2/schedule/events/CALENDAR_TASK/{task_id}/execute",
        headers=headers,
        json={"action": "BLOCK", "reason": "Poste indisponible"},
    ).status_code == 200
    incident_id = client.get(
        "/v2/schedule/incidents",
        headers=headers,
    ).json()["incidents"][0]["id"]

    reassigned = client.post(
        f"/v2/schedule/incidents/{incident_id}/reassign",
        headers=headers,
        json={
            "responsible_user_id": second_worker_id,
            "comment": "Transfert vers le poste ALU",
        },
    )
    assert reassigned.status_code == 200, reassigned.text
    assert reassigned.json()["responsible_user_id"] == second_worker_id
    assert reassigned.json()["history"][-1]["action"] == "REASSIGNED"

    db = session_factory()
    try:
        assert db.get(models.CalendarTask, task_id).assigned_user_id == second_worker_id
        state = db.query(models.ScheduleExecutionState).one()
        assert state.assigned_user_id == second_worker_id
        notification = (
            db.query(models.PlanningNotification)
            .filter(
                models.PlanningNotification.user_id == second_worker_id,
                models.PlanningNotification.notification_type
                == "INCIDENT_REASSIGNED",
            )
            .one()
        )
        assert notification.incident_id == incident_id
    finally:
        db.close()


def test_unacknowledged_planning_incident_escalates_once(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    worker_id = _create_worker(
        session_factory,
        "incident-escalation-worker",
        "Samir",
        "Pose",
        role="OPERATOR",
    )
    _add_alert_rule(
        session_factory,
        code="BLOCKED",
        severity="HIGH",
        escalation_minutes=5,
    )
    start = datetime(2026, 8, 14, 8, 0)
    created = _post_task(
        client,
        headers,
        title="Pose chantier",
        start_at=start,
        end_at=start + timedelta(hours=1),
        assigned_user_id=worker_id,
    )
    task_id = created.json()["source_id"]
    assert client.post(
        f"/v2/schedule/events/CALENDAR_TASK/{task_id}/execute",
        headers=headers,
        json={"action": "BLOCK", "reason": "Accès chantier impossible"},
    ).status_code == 200

    db = session_factory()
    try:
        incident = db.query(models.PlanningIncident).one()
        incident.next_escalation_at = datetime(2026, 8, 14, 8, 5)
        db.commit()
        evaluate_operational_alerts(
            db,
            now=datetime(2026, 8, 14, 8, 6),
        )
        db.commit()
        db.refresh(incident)
        assert incident.escalation_level == 1
        assert incident.next_escalation_at is None
        assert (
            db.query(models.PlanningIncidentHistory)
            .filter(
                models.PlanningIncidentHistory.incident_id == incident.id,
                models.PlanningIncidentHistory.action == "ESCALATED",
            )
            .count()
            == 1
        )
        evaluate_operational_alerts(
            db,
            now=datetime(2026, 8, 14, 9, 0),
        )
        db.commit()
        db.refresh(incident)
        assert incident.escalation_level == 1
    finally:
        db.close()


def test_device_notifications_follow_alert_rule_toggle(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    worker_id = _create_worker(
        session_factory,
        "incident-no-device-worker",
        "Lina",
        "Pose",
        role="OPERATOR",
    )
    _add_alert_rule(
        session_factory,
        code="BLOCKED",
        severity="CRITICAL",
        notify_pwa=False,
        notify_email=False,
    )
    start = datetime(2026, 8, 14, 10, 0)
    created = _post_task(
        client,
        headers,
        title="Pose sans notification appareil",
        start_at=start,
        end_at=start + timedelta(hours=1),
        assigned_user_id=worker_id,
    )
    task_id = created.json()["source_id"]
    assert client.post(
        f"/v2/schedule/events/CALENDAR_TASK/{task_id}/execute",
        headers=headers,
        json={"action": "BLOCK", "reason": "Accès impossible"},
    ).status_code == 200

    db = session_factory()
    try:
        notification_types = {
            item.notification_type
            for item in db.query(models.PlanningNotification).all()
        }
        assert "OPERATIONAL_BLOCKED" in notification_types
        assert "INCIDENT_CRITICAL" not in notification_types
    finally:
        db.close()


def test_admin_updates_operational_alert_rule(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    rule_id = _add_alert_rule(
        session_factory,
        code="PAUSE_TOO_LONG",
        threshold_minutes=30,
    )

    response = client.patch(
        f"/v2/schedule/alert-rules/{rule_id}",
        headers=headers,
        json={
            "threshold_minutes": 45,
            "recipient_mode": "managers",
            "is_active": False,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["threshold_minutes"] == 45
    assert response.json()["recipient_mode"] == "MANAGERS"
    assert response.json()["is_active"] is False


def test_admin_manages_dynamic_execution_reasons(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)

    created = client.post(
        "/v2/schedule/execution-reasons",
        headers=headers,
        json={
            "action": "PAUSE",
            "code": "WAITING_MANAGER",
            "label": "Attente responsable",
            "description": "Validation du responsable nécessaire avant reprise.",
            "requires_comment": True,
            "sort_order": 25,
        },
    )
    assert created.status_code == 201, created.text
    reason_id = created.json()["id"]
    assert created.json()["code"] == "WAITING_MANAGER"
    assert created.json()["requires_comment"] is True

    active = client.get(
        "/v2/schedule/execution-reasons",
        headers=headers,
    )
    assert active.status_code == 200, active.text
    assert [reason["id"] for reason in active.json()] == [reason_id]

    deactivated = client.patch(
        f"/v2/schedule/execution-reasons/{reason_id}",
        headers=headers,
        json={"is_active": False, "label": "Attente validation responsable"},
    )
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["is_active"] is False

    active = client.get(
        "/v2/schedule/execution-reasons",
        headers=headers,
    )
    assert active.json() == []

    all_reasons = client.get(
        "/v2/schedule/execution-reasons",
        headers=headers,
        params={"include_inactive": True},
    )
    assert all_reasons.status_code == 200, all_reasons.text
    assert all_reasons.json()[0]["label"] == "Attente validation responsable"


def test_execution_uses_dynamic_reason_and_requires_detail(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    worker_id, _ = _worker_and_client(session_factory)
    start = datetime(2026, 8, 10, 14, 0)
    task = _post_task(
        client,
        headers,
        title="Contrôler dossier technique",
        start_at=start,
        end_at=start + timedelta(hours=1),
        assigned_user_id=worker_id,
    ).json()
    execution_url = (
        f"/v2/schedule/events/CALENDAR_TASK/{task['source_id']}/execute"
    )
    reason = client.post(
        "/v2/schedule/execution-reasons",
        headers=headers,
        json={
            "action": "PAUSE",
            "code": "OTHER",
            "label": "Autre motif",
            "requires_comment": True,
        },
    )
    assert reason.status_code == 201, reason.text
    assert client.post(
        execution_url,
        headers=headers,
        json={"action": "START"},
    ).status_code == 200

    missing_detail = client.post(
        execution_url,
        headers=headers,
        json={"action": "PAUSE", "reason_code": "OTHER"},
    )
    assert missing_detail.status_code == 422

    paused = client.post(
        execution_url,
        headers=headers,
        json={
            "action": "PAUSE",
            "reason_code": "OTHER",
            "reason": "Réunion sécurité imprévue",
        },
    )
    assert paused.status_code == 200, paused.text
    payload = paused.json()
    assert payload["status"] == "PAUSED"
    assert payload["last_reason_code"] == "OTHER"
    assert payload["last_reason_label"] == "Autre motif"
    assert payload["history"][0]["reason_code"] == "OTHER"
    assert payload["history"][0]["reason_label"] == "Autre motif"
    assert payload["history"][0]["reason"] == "Réunion sécurité imprévue"


def test_operator_executes_only_assigned_task(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    worker_id = _create_worker(
        session_factory,
        "planning-worker",
        "Nina",
        "Atelier",
        role="OPERATOR",
    )
    other_worker_id = _create_worker(
        session_factory,
        "planning-other",
        "Léo",
        "Pose",
        role="OPERATOR",
    )
    start = datetime(2026, 8, 11, 8, 0)
    assigned = _post_task(
        client,
        headers,
        title="Tâche affectée",
        start_at=start,
        end_at=start + timedelta(hours=1),
        assigned_user_id=worker_id,
    ).json()
    other = _post_task(
        client,
        headers,
        title="Tâche d'un collègue",
        start_at=start,
        end_at=start + timedelta(hours=1),
        assigned_user_id=other_worker_id,
    ).json()
    worker_headers = _planning_view_headers("planning-worker")

    own_response = client.post(
        f"/v2/schedule/events/CALENDAR_TASK/{assigned['source_id']}/execute",
        headers=worker_headers,
        json={"action": "START"},
    )
    assert own_response.status_code == 200, own_response.text

    forbidden = client.post(
        f"/v2/schedule/events/CALENDAR_TASK/{other['source_id']}/execute",
        headers=worker_headers,
        json={"action": "START"},
    )
    assert forbidden.status_code == 403


def test_schedule_execution_synchronizes_workshop_status(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    worker_id = _create_worker(
        session_factory,
        "debit-alu",
        "Ali",
        "Débit",
        role="OPERATOR",
    )
    db = session_factory()
    try:
        order = models.Order(reference="CMD-EXEC-001", material="ALU")
        db.add(order)
        db.flush()
        planning = models.Planning(
            order_id=order.id,
            station="ALU_DEBIT",
            assigned_to="debit-alu",
            scheduled_start=datetime(2026, 8, 12, 8, 0),
            scheduled_end=datetime(2026, 8, 12, 10, 0),
        )
        db.add(planning)
        db.commit()
        planning_id = planning.id
    finally:
        db.close()

    base_url = f"/v2/schedule/events/WORKSHOP/{planning_id}/execute"
    started = client.post(
        base_url,
        headers=headers,
        json={"action": "START", "assigned_user_id": worker_id},
    )
    assert started.status_code == 200, started.text
    blocked = client.post(
        base_url,
        headers=headers,
        json={"action": "BLOCK", "reason": "Profilé manquant"},
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["status"] == "BLOCKED"

    db = session_factory()
    try:
        planning = db.get(models.Planning, planning_id)
        assert planning.status == models.PlanningStatus.ISSUE
        assert planning.issue_notes == "Profilé manquant"
    finally:
        db.close()


def test_schedule_resumes_crm_reminder_after_pause(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    worker_id, client_id = _worker_and_client(session_factory)
    db = session_factory()
    try:
        opportunity = models.CRMOpportunity(
            reference="OPP-EXEC-REMINDER",
            client_id=client_id,
            owner_user_id=worker_id,
            title="Relance chantier ASTAURIA",
        )
        rule = models.CRMReminderRule(
            name="Relance test planning",
            stage=models.CRMOpportunityStage.NEW.value,
            delay_days=2,
            created_by="schedule-admin",
        )
        db.add_all([opportunity, rule])
        db.flush()
        reminder = models.CRMReminderPlan(
            plan_key="REMINDER-EXEC-001",
            rule_id=rule.id,
            opportunity_id=opportunity.id,
            client_id=client_id,
            assigned_user_id=worker_id,
            stage_snapshot=models.CRMOpportunityStage.NEW.value,
            due_at=datetime(2026, 8, 13, 10, 0),
            created_by="schedule-admin",
        )
        db.add(reminder)
        db.commit()
        reminder_id = reminder.id
    finally:
        db.close()

    execution_url = f"/v2/schedule/events/CRM_REMINDER/{reminder_id}/execute"
    started = client.post(
        execution_url,
        headers=headers,
        json={"action": "START"},
    )
    assert started.status_code == 200, started.text

    paused = client.post(
        execution_url,
        headers=headers,
        json={"action": "PAUSE", "reason": "Pause déjeuner"},
    )
    assert paused.status_code == 200, paused.text
    assert paused.json()["status"] == "PAUSED"

    resumed = client.post(
        execution_url,
        headers=headers,
        json={"action": "START", "note": "Reprise de la relance"},
    )
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["status"] == "IN_PROGRESS"
    assert [item["action"] for item in resumed.json()["history"]] == [
        "START",
        "PAUSE",
        "START",
    ]


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


def test_planning_resources_members_and_unavailability(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    worker_id, _ = _worker_and_client(session_factory)

    resource = client.post(
        "/v2/schedule/resources",
        headers=headers,
        json={
            "code": "VEH-METRE-01",
            "name": "Fourgon métreur",
            "resource_type": "VEHICLE",
            "capacity": 1,
        },
    )
    assert resource.status_code == 201, resource.text
    resource_id = resource.json()["id"]

    members = client.put(
        f"/v2/schedule/resources/{resource_id}/members",
        headers=headers,
        json={
            "members": [
                {
                    "user_id": worker_id,
                    "member_role": "RESPONSABLE",
                    "is_lead": True,
                }
            ]
        },
    )
    assert members.status_code == 200, members.text
    assert members.json()["members"][0]["user_id"] == worker_id
    assert members.json()["members"][0]["is_lead"] is True

    unavailable = client.post(
        f"/v2/schedule/resources/{resource_id}/unavailabilities",
        headers=headers,
        json={
            "resource_id": resource_id,
            "start_at": "2026-08-03T08:00:00Z",
            "end_at": "2026-08-03T12:00:00Z",
            "reason": "Révision annuelle",
            "unavailability_type": "MAINTENANCE",
        },
    )
    assert unavailable.status_code == 201, unavailable.text

    listed = client.get(
        f"/v2/schedule/resources/{resource_id}/unavailabilities",
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["reason"] == "Révision annuelle"

    deleted = client.delete(
        f"/v2/schedule/resources/unavailabilities/{unavailable.json()['id']}",
        headers=headers,
    )
    assert deleted.status_code == 200, deleted.text


def test_regulated_skill_requires_expiry_date(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    worker_id = _create_worker(
        session_factory,
        "planning-certified",
        "Nora",
        "Sécurité",
    )
    created = client.post(
        "/v2/schedule/skills",
        headers=headers,
        json={
            "code": "TEST_CACES",
            "name": "CACES de test",
            "category": "CERTIFICATION",
            "requires_expiry": True,
        },
    )
    assert created.status_code == 201, created.text
    skill_id = created.json()["id"]

    missing_expiry = client.put(
        f"/v2/schedule/users/{worker_id}/skills",
        headers=headers,
        json={
            "skills": [
                {
                    "skill_id": skill_id,
                    "level": 3,
                    "is_certified": True,
                    "certificate_reference": "CERT-2026-001",
                }
            ]
        },
    )
    assert missing_expiry.status_code == 422, missing_expiry.text
    assert "Date de validité obligatoire" in missing_expiry.json()["detail"]

    assigned = client.put(
        f"/v2/schedule/users/{worker_id}/skills",
        headers=headers,
        json={
            "skills": [
                {
                    "skill_id": skill_id,
                    "level": 3,
                    "is_certified": True,
                    "certificate_reference": "CERT-2026-001",
                    "valid_until": "2028-12-31T23:59:59",
                }
            ]
        },
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()[0]["certificate_reference"] == "CERT-2026-001"
    assert assigned.json()[0]["valid_until"].startswith("2028-12-31")


def test_assignment_creates_notification_and_auditable_history(isolated_client):
    client, session_factory = isolated_client
    headers = _admin_headers(session_factory)
    worker_id = _create_worker(
        session_factory,
        "planning-notified",
        "Mila",
        "Pose",
        role="OPERATOR",
    )
    start = datetime(2026, 8, 6, 9, 0)
    created = _post_task(
        client,
        headers,
        title="Pose chantier République",
        start_at=start,
        end_at=start + timedelta(hours=2),
        assigned_user_id=worker_id,
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["source_id"]

    history = client.get(
        f"/v2/schedule/tasks/{task_id}/history",
        headers=headers,
    )
    assert history.status_code == 200, history.text
    assert history.json()[0]["action"] == "CREATED"

    personal_headers = _planning_view_headers("planning-notified")
    notifications = client.get(
        "/v2/schedule/notifications",
        headers=personal_headers,
    )
    assert notifications.status_code == 200, notifications.text
    assert notifications.json()[0]["notification_type"] == "ASSIGNMENT"

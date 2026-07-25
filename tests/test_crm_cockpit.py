from datetime import datetime, timedelta
from types import SimpleNamespace

from backend.services.crm_cockpit import build_crm_cockpit


NOW = datetime(2026, 7, 25, 9, 0, 0)


def client(name="Menuiserie Test"):
    return SimpleNamespace(name=name)


def opportunity(
    item_id,
    *,
    stage="qualifie",
    amount=10000,
    probability=50,
    milestone="Valider le besoin",
    milestone_at=None,
    updated_at=None,
):
    return SimpleNamespace(
        id=item_id,
        reference=f"OPP-2026-{item_id:05d}",
        client_id=item_id,
        client=client(f"Client {item_id}"),
        stage=stage,
        estimated_amount=amount,
        probability=probability,
        next_milestone=milestone,
        next_milestone_at=milestone_at,
        updated_at=updated_at or NOW,
        title=f"Projet {item_id}",
        owner=None,
        owner_name="Commercial",
    )


def activity(item_id, *, opportunity_id=1, due_at=None, status="a_faire"):
    return SimpleNamespace(
        id=item_id,
        client_id=opportunity_id,
        client=client(f"Client {opportunity_id}"),
        opportunity_id=opportunity_id,
        opportunity_reference=f"OPP-2026-{opportunity_id:05d}",
        subject=f"Relance {item_id}",
        due_at=due_at,
        status=status,
        author="commercial",
    )


def mission(item_id, *, scheduled_start=None, status="TO_SCHEDULE"):
    return SimpleNamespace(
        id=item_id,
        reference=f"MET-2026-{item_id:05d}",
        client_id=item_id,
        client=client(f"Client {item_id}"),
        opportunity_id=item_id,
        purpose="Relevé chantier",
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_start + timedelta(hours=2) if scheduled_start else None,
        status=status,
        assigned_user=None,
    )


def test_cockpit_calculates_weighted_pipeline_and_stage_totals():
    result = build_crm_cockpit(
        [
            opportunity(1, amount=10000, probability=50),
            opportunity(2, stage="negociation", amount=20000, probability=75),
            opportunity(3, stage="gagne", amount=90000, probability=100),
        ],
        [],
        [],
        now=NOW,
    )

    assert result["metrics"]["open_opportunities"] == 2
    assert result["metrics"]["pipeline_amount"] == 30000
    assert result["metrics"]["weighted_pipeline_amount"] == 20000
    negotiation = next(item for item in result["stages"] if item["stage"] == "negociation")
    assert negotiation == {
        "stage": "negociation",
        "count": 1,
        "amount": 20000,
        "weighted_amount": 15000,
    }


def test_cockpit_prioritizes_overdue_actions_and_unscheduled_measures():
    result = build_crm_cockpit(
        [opportunity(1, milestone_at=NOW + timedelta(days=3))],
        [activity(1, due_at=NOW - timedelta(days=1))],
        [mission(1)],
        now=NOW,
    )

    assert result["metrics"]["overdue_actions"] == 1
    assert result["metrics"]["measures_to_schedule"] == 1
    assert result["reminders"][0]["kind"] == "OVERDUE_ACTIVITY"
    assert any(item["kind"] == "UNSCHEDULED_MEASURE" for item in result["reminders"])
    assert any(item["kind"] == "MEASURE" and item["start_at"] is None for item in result["agenda"])


def test_cockpit_detects_stale_opportunity_without_open_activity():
    result = build_crm_cockpit(
        [
            opportunity(
                1,
                stage="proposition_envoyee",
                updated_at=NOW - timedelta(days=10),
                milestone_at=NOW + timedelta(days=2),
            )
        ],
        [],
        [],
        now=NOW,
        stale_days=7,
    )

    reminder = next(item for item in result["reminders"] if item["kind"] == "STALE_OPPORTUNITY")
    assert reminder["severity"] == "HIGH"
    assert reminder["client_id"] == 1


def test_open_activity_prevents_duplicate_stale_reminder():
    result = build_crm_cockpit(
        [
            opportunity(
                1,
                updated_at=NOW - timedelta(days=10),
                milestone_at=NOW + timedelta(days=2),
            )
        ],
        [activity(1, opportunity_id=1, due_at=NOW + timedelta(days=1))],
        [],
        now=NOW,
        stale_days=7,
    )

    assert not any(item["kind"] == "STALE_OPPORTUNITY" for item in result["reminders"])

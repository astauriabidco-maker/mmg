from datetime import datetime, timedelta
from types import SimpleNamespace

from backend.services.crm_cockpit import build_crm_cockpit


NOW = datetime(2026, 7, 25, 9, 0, 0)


def client(name="Menuiserie Test"):
    return SimpleNamespace(name=name)


def client_with_primary_contact_email():
    return SimpleNamespace(
        name="Client contact",
        email="",
        contacts=[
            SimpleNamespace(
                id=2,
                name="Secondaire",
                email="secondaire@example.test",
                is_primary=False,
            ),
            SimpleNamespace(
                id=1,
                name="Principal",
                email="principal@example.test",
                is_primary=True,
            ),
        ],
    )


def opportunity(
    item_id,
    *,
    stage="qualifie",
    amount=10000,
    probability=50,
    milestone="Valider le besoin",
    milestone_at=None,
    updated_at=None,
    owner_user_id=1,
    owner_name="Commercial",
    sale_order_id=None,
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
        owner_user_id=owner_user_id,
        owner_name=owner_name,
        sale_order_id=sale_order_id,
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


def reminder_plan(
    item_id,
    *,
    opportunity_id=1,
    due_at=None,
    assigned_user_id=1,
    assigned_user_name="Commercial",
):
    first_name, *last_name = assigned_user_name.split(" ")
    opportunity_item = opportunity(
        opportunity_id,
        owner_user_id=assigned_user_id,
        owner_name=assigned_user_name,
    )
    return SimpleNamespace(
        id=item_id,
        plan_key=f"CRM-PLAN-{item_id}",
        opportunity_id=opportunity_id,
        opportunity=opportunity_item,
        client_id=opportunity_id,
        client=opportunity_item.client,
        assigned_user_id=assigned_user_id,
        assigned_user=SimpleNamespace(
            first_name=first_name,
            last_name=" ".join(last_name) or None,
            username=assigned_user_name.lower(),
        ),
        rule=SimpleNamespace(name="Relancer la proposition"),
        due_at=due_at,
        status="PENDING",
    )


def stage_event(item_id, from_stage, to_stage):
    return SimpleNamespace(
        opportunity_id=item_id,
        from_stage=from_stage,
        to_stage=to_stage,
    )


def sale_order(item_id, *, status="SENT", lines=None):
    return SimpleNamespace(
        id=item_id,
        status=status,
        lines=lines or [],
    )


def sale_line(*, quantity=1, unit_price=1000, discount_pct=0):
    return SimpleNamespace(
        quantity=quantity,
        unit_price=unit_price,
        discount_pct=discount_pct,
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


def test_cockpit_reminder_uses_primary_contact_email_when_client_email_is_empty():
    item = opportunity(
        1,
        stage="proposition_envoyee",
        updated_at=NOW - timedelta(days=10),
        milestone_at=NOW + timedelta(days=2),
    )
    item.client = client_with_primary_contact_email()

    result = build_crm_cockpit(
        [item],
        [],
        [],
        now=NOW,
        stale_days=7,
    )

    reminder = next(item for item in result["reminders"] if item["kind"] == "STALE_OPPORTUNITY")
    assert reminder["client_email"] == "principal@example.test"


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


def test_cockpit_groups_today_overdue_and_missing_actions_by_owner():
    result = build_crm_cockpit(
        [
            opportunity(1, milestone=None, milestone_at=None),
            opportunity(
                2,
                milestone_at=NOW + timedelta(days=2),
                owner_user_id=2,
                owner_name="Alice Martin",
            ),
            opportunity(
                3,
                milestone_at=NOW - timedelta(days=2),
                updated_at=NOW - timedelta(days=1),
                owner_user_id=2,
                owner_name="Alice Martin",
            ),
        ],
        [],
        [],
        reminder_plans=[
            reminder_plan(1, due_at=NOW.replace(hour=15)),
            reminder_plan(
                2,
                opportunity_id=2,
                due_at=NOW - timedelta(days=2),
                assigned_user_id=2,
                assigned_user_name="Alice Martin",
            ),
        ],
        now=NOW,
    )

    assert result["metrics"]["reminders_today"] == 1
    assert result["metrics"]["overdue_reminders"] == 1
    assert result["metrics"]["opportunities_without_action"] == 2
    assert [item["id"] for item in result["opportunities_without_action"]] == [3, 1]
    commercial = next(item for item in result["owners"] if item["owner_user_id"] == 1)
    alice = next(item for item in result["owners"] if item["owner_user_id"] == 2)
    assert commercial["reminders_today"] == 1
    assert commercial["opportunities_without_action"] == 1
    assert alice["overdue_reminders"] == 1
    assert alice["opportunities_without_action"] == 1


def test_cockpit_computes_commercial_steering_by_owner():
    result = build_crm_cockpit(
        [
            opportunity(
                1,
                amount=10000,
                probability=50,
                sale_order_id=10,
                milestone_at=NOW + timedelta(days=3),
            ),
            opportunity(
                2,
                amount=8000,
                probability=25,
                sale_order_id=11,
                milestone=None,
                milestone_at=None,
            ),
        ],
        [],
        [],
        sale_orders=[
            sale_order(10, status="SENT"),
            sale_order(
                11,
                status="VALIDATED",
                lines=[
                    sale_line(quantity=2, unit_price=1500),
                    sale_line(quantity=1, unit_price=1000, discount_pct=10),
                ],
            ),
        ],
        now=NOW,
    )

    owner = result["owners"][0]
    assert owner["pipeline_amount"] == 18000
    assert owner["weighted_pipeline_amount"] == 7000
    assert owner["quotes_sent"] == 1
    assert owner["quotes_signed"] == 1
    assert owner["signed_amount"] == 3900
    assert owner["conversion_rate"] == 50
    assert owner["attention_score"] == 2
    assert result["metrics"]["quotes_sent"] == 1
    assert result["metrics"]["quotes_signed"] == 1
    assert result["metrics"]["signed_amount"] == 3900
    assert result["metrics"]["conversion_rate"] == 50


def test_cockpit_conversion_rates_use_real_stage_transitions():
    result = build_crm_cockpit(
        [],
        [],
        [],
        stage_history=[
            stage_event(1, None, "nouveau"),
            stage_event(1, "nouveau", "qualifie"),
            stage_event(2, None, "nouveau"),
            stage_event(2, "nouveau", "perdu"),
            stage_event(3, None, "qualifie"),
            stage_event(4, None, "negociation"),
            stage_event(4, "negociation", "proposition_envoyee"),
        ],
        now=NOW,
    )

    new_stage = next(item for item in result["stage_conversions"] if item["stage"] == "nouveau")
    qualified = next(item for item in result["stage_conversions"] if item["stage"] == "qualifie")
    assert new_stage == {
        "stage": "nouveau",
        "entered_count": 2,
        "advanced_count": 1,
        "lost_count": 1,
        "decided_count": 2,
        "conversion_rate": 50.0,
    }
    assert qualified["entered_count"] == 2
    assert qualified["conversion_rate"] is None
    negotiation = next(
        item for item in result["stage_conversions"]
        if item["stage"] == "negociation"
    )
    assert negotiation["entered_count"] == 1
    assert negotiation["advanced_count"] == 0
    assert negotiation["conversion_rate"] is None

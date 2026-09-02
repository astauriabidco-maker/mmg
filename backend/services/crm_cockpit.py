from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal


OPEN_OPPORTUNITY_STAGES = {
    "nouveau",
    "qualifie",
    "metre_a_planifier",
    "metre_en_cours",
    "proposition_a_preparer",
    "proposition_a_valider",
    "proposition_envoyee",
    "negociation",
}

STAGE_ORDER = (
    "nouveau",
    "qualifie",
    "metre_a_planifier",
    "metre_en_cours",
    "proposition_a_preparer",
    "proposition_a_valider",
    "proposition_envoyee",
    "negociation",
)
STAGE_POSITION = {stage: index for index, stage in enumerate(STAGE_ORDER)}

OPEN_MEASURE_STATUSES = {
    "DRAFT",
    "TO_SCHEDULE",
    "SCHEDULED",
    "IN_CAPTURE",
    "ON_SITE",
    "TO_REVIEW",
    "CORRECTION_REQUIRED",
}


def _naive_utc(value):
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _number(value):
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _client_name(item):
    client = getattr(item, "client", None)
    return getattr(client, "name", None) or getattr(item, "client_name", None) or "Client"


def _client_email(item):
    client = getattr(item, "client", None)
    direct_email = (getattr(client, "email", None) or "").strip() if client else ""
    if direct_email:
        return direct_email
    contacts = sorted(
        getattr(client, "contacts", None) or [],
        key=lambda contact: (
            not getattr(contact, "is_primary", False),
            getattr(contact, "name", "") or "",
            getattr(contact, "id", 0) or 0,
        ),
    )
    for contact in contacts:
        contact_email = (getattr(contact, "email", None) or "").strip()
        if contact_email:
            return contact_email
    return getattr(item, "client_email", None)


def _owner_name(opportunity):
    owner_name = getattr(opportunity, "owner_name", None)
    if owner_name:
        return owner_name
    owner = getattr(opportunity, "owner", None)
    if not owner:
        return None
    full_name = " ".join(
        value
        for value in [getattr(owner, "first_name", None), getattr(owner, "last_name", None)]
        if value
    )
    return full_name or getattr(owner, "username", None)


def _assigned_name(mission):
    user = getattr(mission, "assigned_user", None)
    if not user:
        return None
    full_name = " ".join(
        value
        for value in [getattr(user, "first_name", None), getattr(user, "last_name", None)]
        if value
    )
    return full_name or getattr(user, "username", None)


def _user_name(user):
    if not user:
        return None
    full_name = " ".join(
        value
        for value in [getattr(user, "first_name", None), getattr(user, "last_name", None)]
        if value
    )
    return full_name or getattr(user, "username", None)


def build_crm_cockpit(
    opportunities,
    activities,
    missions,
    *,
    reminder_plans=None,
    stage_history=None,
    now=None,
    horizon_days=14,
    stale_days=7,
):
    reminder_plans = reminder_plans or []
    stage_history = stage_history or []
    now = _naive_utc(now or datetime.utcnow())
    horizon = now + timedelta(days=horizon_days)
    stale_before = now - timedelta(days=stale_days)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)

    open_opportunities = [
        item for item in opportunities if str(getattr(item, "stage", "")) in OPEN_OPPORTUNITY_STAGES
    ]
    open_activities = [
        item for item in activities if str(getattr(item, "status", "")) == "a_faire"
    ]
    open_missions = [
        item for item in missions if str(getattr(item, "status", "")) in OPEN_MEASURE_STATUSES
    ]

    stage_totals = defaultdict(lambda: {"count": 0, "amount": 0.0, "weighted_amount": 0.0})
    for opportunity in open_opportunities:
        stage = str(getattr(opportunity, "stage", "nouveau"))
        amount = _number(getattr(opportunity, "estimated_amount", 0))
        probability = max(0, min(100, int(getattr(opportunity, "probability", 0) or 0)))
        stage_totals[stage]["count"] += 1
        stage_totals[stage]["amount"] += amount
        stage_totals[stage]["weighted_amount"] += amount * probability / 100

    stages = [
        {
            "stage": stage,
            "count": stage_totals[stage]["count"],
            "amount": round(stage_totals[stage]["amount"], 2),
            "weighted_amount": round(stage_totals[stage]["weighted_amount"], 2),
        }
        for stage in STAGE_ORDER
    ]

    agenda = []
    for activity in open_activities:
        due_at = _naive_utc(getattr(activity, "due_at", None))
        if due_at is None or due_at <= horizon:
            agenda.append(
                {
                    "kind": "ACTIVITY",
                    "id": getattr(activity, "id", 0),
                    "client_id": getattr(activity, "client_id", 0),
                    "client_name": _client_name(activity),
                    "target_id": activity.id,
                    "opportunity_id": getattr(activity, "opportunity_id", None),
                    "reference": getattr(activity, "opportunity_reference", None),
                    "title": getattr(activity, "subject", "Activité CRM"),
                    "start_at": due_at,
                    "end_at": None,
                    "status": getattr(activity, "status", "a_faire"),
                    "owner_name": getattr(activity, "author", None),
                    "overdue": bool(due_at and due_at < now),
                }
            )

    for mission in open_missions:
        scheduled_start = _naive_utc(getattr(mission, "scheduled_start", None))
        if scheduled_start is None or scheduled_start <= horizon:
            agenda.append(
                {
                    "kind": "MEASURE",
                    "id": getattr(mission, "id", 0),
                    "client_id": getattr(mission, "client_id", 0),
                    "client_name": _client_name(mission),
                    "opportunity_id": getattr(mission, "opportunity_id", None),
                    "reference": getattr(mission, "reference", None),
                    "title": getattr(mission, "purpose", None) or "Mission de métré",
                    "start_at": scheduled_start,
                    "end_at": _naive_utc(getattr(mission, "scheduled_end", None)),
                    "status": getattr(mission, "status", "TO_SCHEDULE"),
                    "owner_name": _assigned_name(mission),
                    "overdue": bool(
                        scheduled_start
                        and scheduled_start < now
                        and str(getattr(mission, "status", "")) in {"TO_SCHEDULE", "SCHEDULED"}
                    ),
                }
            )

    agenda.sort(
        key=lambda item: (
            item["start_at"] is None,
            item["start_at"] or datetime.max,
            item["kind"],
        )
    )

    open_activity_by_opportunity = defaultdict(list)
    for activity in open_activities:
        if getattr(activity, "opportunity_id", None):
            open_activity_by_opportunity[activity.opportunity_id].append(activity)

    opportunities_without_action = []
    for opportunity in open_opportunities:
        milestone_at = _naive_utc(getattr(opportunity, "next_milestone_at", None))
        if open_activity_by_opportunity.get(opportunity.id) or (
            milestone_at is not None and milestone_at > now
        ):
            continue
        opportunities_without_action.append(
            {
                "id": opportunity.id,
                "reference": opportunity.reference,
                "client_id": opportunity.client_id,
                "client_name": _client_name(opportunity),
                "client_email": _client_email(opportunity),
                "title": opportunity.title,
                "stage": opportunity.stage,
                "owner_user_id": getattr(opportunity, "owner_user_id", None),
                "owner_name": _owner_name(opportunity),
                "amount": round(_number(getattr(opportunity, "estimated_amount", 0)), 2),
                "updated_at": _naive_utc(getattr(opportunity, "updated_at", None)),
            }
        )
    opportunities_without_action.sort(
        key=lambda item: (item["updated_at"] or datetime.min, item["reference"])
    )

    reminders = []
    seen_keys = set()

    def add_reminder(payload):
        if payload["key"] in seen_keys:
            return
        seen_keys.add(payload["key"])
        reminders.append(payload)

    for activity in open_activities:
        due_at = _naive_utc(getattr(activity, "due_at", None))
        if due_at and due_at < now:
            add_reminder(
                {
                    "key": f"activity-overdue-{activity.id}",
                    "kind": "OVERDUE_ACTIVITY",
                    "severity": "CRITICAL",
                    "client_id": activity.client_id,
                    "client_name": _client_name(activity),
                    "client_email": _client_email(activity),
                    "opportunity_id": getattr(activity, "opportunity_id", None),
                    "reference": getattr(activity, "opportunity_reference", None),
                    "title": getattr(activity, "subject", "Relance échue"),
                    "reason": "Cette activité commerciale est arrivée à échéance.",
                    "suggested_subject": getattr(activity, "subject", "Relancer le client"),
                    "due_at": due_at,
                    "existing_activity_id": activity.id,
                }
            )

    for opportunity in open_opportunities:
        milestone_at = _naive_utc(getattr(opportunity, "next_milestone_at", None))
        updated_at = _naive_utc(getattr(opportunity, "updated_at", None))
        common = {
            "client_id": opportunity.client_id,
            "client_name": _client_name(opportunity),
            "client_email": _client_email(opportunity),
            "target_id": opportunity.id,
            "opportunity_id": opportunity.id,
            "reference": getattr(opportunity, "reference", None),
            "existing_activity_id": None,
        }

        if milestone_at and milestone_at < now:
            add_reminder(
                {
                    **common,
                    "key": f"milestone-overdue-{opportunity.id}",
                    "kind": "OVERDUE_MILESTONE",
                    "severity": "HIGH",
                    "title": getattr(opportunity, "title", "Opportunité à relancer"),
                    "reason": "Le prochain jalon commercial est dépassé.",
                    "suggested_subject": (
                        getattr(opportunity, "next_milestone", None)
                        or f"Relancer {_client_name(opportunity)}"
                    ),
                    "due_at": milestone_at,
                }
            )
        elif (
            not open_activity_by_opportunity.get(opportunity.id)
            and (
                not getattr(opportunity, "next_milestone", None)
                or milestone_at is None
            )
        ):
            add_reminder(
                {
                    **common,
                    "key": f"milestone-missing-{opportunity.id}",
                    "kind": "MISSING_NEXT_STEP",
                    "severity": "MEDIUM",
                    "title": getattr(opportunity, "title", "Opportunité sans prochaine action"),
                    "reason": "Aucun prochain jalon daté n'est défini.",
                    "suggested_subject": f"Définir la prochaine action avec {_client_name(opportunity)}",
                    "due_at": None,
                }
            )

        if (
            updated_at
            and updated_at < stale_before
            and not open_activity_by_opportunity.get(opportunity.id)
        ):
            add_reminder(
                {
                    **common,
                    "key": f"opportunity-stale-{opportunity.id}",
                    "kind": "STALE_OPPORTUNITY",
                    "severity": "HIGH"
                    if str(getattr(opportunity, "stage", "")) in {"proposition_envoyee", "negociation"}
                    else "MEDIUM",
                    "title": getattr(opportunity, "title", "Opportunité sans activité"),
                    "reason": f"Aucune activité ouverte depuis plus de {stale_days} jours.",
                    "suggested_subject": f"Relancer {_client_name(opportunity)}",
                    "due_at": None,
                }
            )

    for mission in open_missions:
        if getattr(mission, "scheduled_start", None) is None:
            add_reminder(
                {
                    "key": f"measure-unscheduled-{mission.id}",
                    "kind": "UNSCHEDULED_MEASURE",
                    "severity": "HIGH",
                    "client_id": mission.client_id,
                    "client_name": _client_name(mission),
                    "client_email": _client_email(mission),
                    "target_id": mission.id,
                    "opportunity_id": getattr(mission, "opportunity_id", None),
                    "reference": getattr(mission, "reference", None),
                    "title": getattr(mission, "purpose", None) or "Métré à planifier",
                    "reason": "La mission de métré n'a ni date ni créneau.",
                    "suggested_subject": f"Planifier le métré {_client_name(mission)}",
                    "due_at": None,
                    "existing_activity_id": None,
                }
            )

    severity_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    reminders.sort(
        key=lambda item: (
            severity_rank.get(item["severity"], 9),
            item["due_at"] is None,
            item["due_at"] or datetime.max,
        )
    )

    planned_today = []
    planned_overdue = []
    for plan in reminder_plans:
        if str(getattr(plan, "status", "")) != "PENDING":
            continue
        due_at = _naive_utc(getattr(plan, "due_at", None))
        if due_at is None or due_at >= tomorrow_start:
            continue
        opportunity = getattr(plan, "opportunity", None)
        client = getattr(plan, "client", None) or getattr(opportunity, "client", None)
        payload = {
            "key": getattr(plan, "plan_key", f"planned-{getattr(plan, 'id', 0)}"),
            "kind": "PLANNED_REMINDER",
            "severity": "CRITICAL" if due_at < today_start else "HIGH",
            "client_id": getattr(plan, "client_id", 0),
            "client_name": getattr(client, "name", None) or _client_name(opportunity),
            "client_email": getattr(client, "email", None),
            "target_id": getattr(plan, "id", None),
            "opportunity_id": getattr(plan, "opportunity_id", None),
            "reference": getattr(opportunity, "reference", None),
            "title": getattr(opportunity, "title", None) or "Relance commerciale",
            "reason": (
                "La relance planifiée est en retard."
                if due_at < today_start
                else "La relance planifiée doit être validée aujourd'hui."
            ),
            "suggested_subject": getattr(getattr(plan, "rule", None), "name", None)
            or "Relancer le client",
            "due_at": due_at,
            "existing_activity_id": None,
        }
        if due_at < today_start:
            planned_overdue.append(payload)
        else:
            planned_today.append(payload)
    planned_today.sort(key=lambda item: item["due_at"])
    planned_overdue.sort(key=lambda item: item["due_at"])

    owner_rows = {}

    def owner_row(user_id, name):
        key = user_id if user_id is not None else "unassigned"
        if key not in owner_rows:
            owner_rows[key] = {
                "owner_user_id": user_id,
                "owner_name": name or "Non affecté",
                "open_opportunities": 0,
                "pipeline_amount": 0.0,
                "reminders_today": 0,
                "overdue_reminders": 0,
                "opportunities_without_action": 0,
            }
        return owner_rows[key]

    without_action_ids = {item["id"] for item in opportunities_without_action}
    for opportunity in open_opportunities:
        row = owner_row(
            getattr(opportunity, "owner_user_id", None),
            _owner_name(opportunity),
        )
        row["open_opportunities"] += 1
        row["pipeline_amount"] += _number(getattr(opportunity, "estimated_amount", 0))
        if opportunity.id in without_action_ids:
            row["opportunities_without_action"] += 1

    for plan in reminder_plans:
        if str(getattr(plan, "status", "")) != "PENDING":
            continue
        due_at = _naive_utc(getattr(plan, "due_at", None))
        if due_at is None or due_at >= tomorrow_start:
            continue
        row = owner_row(
            getattr(plan, "assigned_user_id", None),
            _user_name(getattr(plan, "assigned_user", None)),
        )
        if due_at < today_start:
            row["overdue_reminders"] += 1
        else:
            row["reminders_today"] += 1

    owners = []
    for row in owner_rows.values():
        row["pipeline_amount"] = round(row["pipeline_amount"], 2)
        owners.append(row)
    owners.sort(
        key=lambda item: (
            -item["overdue_reminders"],
            -item["opportunities_without_action"],
            item["owner_name"],
        )
    )

    entered_by_stage = defaultdict(set)
    advanced_by_stage = defaultdict(set)
    lost_by_stage = defaultdict(set)
    for event in stage_history:
        opportunity_id = getattr(event, "opportunity_id", None)
        to_stage = str(getattr(event, "to_stage", "") or "")
        from_stage = str(getattr(event, "from_stage", "") or "")
        if opportunity_id is None:
            continue
        if to_stage in STAGE_ORDER:
            entered_by_stage[to_stage].add(opportunity_id)
        if from_stage in STAGE_ORDER:
            if to_stage == "perdu":
                lost_by_stage[from_stage].add(opportunity_id)
            elif to_stage == "gagne" or (
                to_stage in STAGE_POSITION
                and STAGE_POSITION[to_stage] > STAGE_POSITION[from_stage]
            ):
                advanced_by_stage[from_stage].add(opportunity_id)

    stage_conversions = []
    for stage in STAGE_ORDER:
        advanced_count = len(advanced_by_stage[stage])
        lost_count = len(lost_by_stage[stage])
        decided_count = advanced_count + lost_count
        stage_conversions.append(
            {
                "stage": stage,
                "entered_count": len(entered_by_stage[stage]),
                "advanced_count": advanced_count,
                "lost_count": lost_count,
                "decided_count": decided_count,
                "conversion_rate": (
                    round(advanced_count * 100 / decided_count, 1)
                    if decided_count
                    else None
                ),
            }
        )

    total_pipeline = sum(_number(item.estimated_amount) for item in open_opportunities)
    weighted_pipeline = sum(
        _number(item.estimated_amount) * max(0, min(100, int(item.probability or 0))) / 100
        for item in open_opportunities
    )
    overdue_actions = sum(
        1
        for item in open_activities
        if _naive_utc(getattr(item, "due_at", None))
        and _naive_utc(item.due_at) < now
    )
    measures_to_schedule = sum(
        1 for item in open_missions if getattr(item, "scheduled_start", None) is None
    )

    return {
        "generated_at": now,
        "horizon_days": horizon_days,
        "metrics": {
            "open_opportunities": len(open_opportunities),
            "pipeline_amount": round(total_pipeline, 2),
            "weighted_pipeline_amount": round(weighted_pipeline, 2),
            "overdue_actions": overdue_actions,
            "reminders_today": len(planned_today),
            "overdue_reminders": len(planned_overdue),
            "opportunities_without_action": len(opportunities_without_action),
            "measures_to_schedule": measures_to_schedule,
            "automatic_reminders": len(reminders),
        },
        "stages": stages,
        "agenda": agenda,
        "reminders": reminders,
        "reminders_today": planned_today,
        "overdue_reminders": planned_overdue,
        "opportunities_without_action": opportunities_without_action,
        "owners": owners,
        "stage_conversions": stage_conversions,
    }

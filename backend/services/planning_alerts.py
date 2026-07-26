from datetime import datetime
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .. import models
from ..core.security import roles_have_permission
from ..core.time import utcnow


ALERT_RULE_CODES = {"BLOCKED", "PAUSE_TOO_LONG", "DURATION_OVERRUN"}
RECIPIENT_MODES = {"RESPONSIBLE", "MANAGERS", "BOTH"}
DEFAULT_SOURCE_MINUTES = {
    "CALENDAR_TASK": 60,
    "CRM_ACTIVITY": 30,
    "CRM_MILESTONE": 45,
    "CRM_REMINDER": 20,
    "MEASURE_MISSION": 120,
    "WORKSHOP": 90,
    "DELIVERY": 240,
}


def serialize_alert_rule(rule: models.PlanningAlertRule) -> dict:
    return {
        "id": rule.id,
        "code": rule.code,
        "label": rule.label,
        "description": rule.description,
        "threshold_minutes": rule.threshold_minutes,
        "recipient_mode": rule.recipient_mode,
        "is_active": rule.is_active,
        "updated_at": rule.updated_at,
    }


def _manager_ids(db: Session) -> set[int]:
    managers = set()
    users = (
        db.query(models.User)
        .options(selectinload(models.User.secondary_roles))
        .filter(models.User.is_active == True)  # noqa: E712
        .all()
    )
    for user in users:
        if roles_have_permission(db, user.role_names, "PLANNING_EDIT"):
            managers.add(user.id)
    return managers


def _recipient_ids(
    db: Session,
    rule: models.PlanningAlertRule,
    responsible_user_id: Optional[int],
) -> set[int]:
    recipients = set()
    if rule.recipient_mode in {"RESPONSIBLE", "BOTH"} and responsible_user_id:
        recipients.add(responsible_user_id)
    if rule.recipient_mode in {"MANAGERS", "BOTH"}:
        recipients.update(_manager_ids(db))
    return recipients


def _source_snapshot(
    db: Session,
    state: models.ScheduleExecutionState,
) -> tuple[str, Optional[int], int]:
    planned_minutes = DEFAULT_SOURCE_MINUTES.get(state.source_type, 60)
    task_id = state.source_id if state.source_type == "CALENDAR_TASK" else None
    title = f"{state.source_type} #{state.source_id}"
    if state.source_type == "CALENDAR_TASK":
        task = db.get(models.CalendarTask, state.source_id)
        if task:
            title = task.title
            if task.workload_minutes and task.workload_minutes > 0:
                planned_minutes = int(task.workload_minutes)
            elif task.start_at and task.end_at:
                planned_minutes = max(
                    1,
                    int((task.end_at - task.start_at).total_seconds() // 60),
                )
    return title, task_id, planned_minutes


def _elapsed_minutes(
    state: models.ScheduleExecutionState,
    now: datetime,
) -> int:
    elapsed = int(state.elapsed_minutes or 0)
    if state.status == "IN_PROGRESS" and state.active_since:
        elapsed += max(
            0,
            int((now - state.active_since).total_seconds() // 60),
        )
    return elapsed


def _latest_log(
    db: Session,
    state_id: int,
    action: str,
) -> Optional[models.ScheduleExecutionLog]:
    return (
        db.query(models.ScheduleExecutionLog)
        .filter(
            models.ScheduleExecutionLog.state_id == state_id,
            models.ScheduleExecutionLog.action == action,
        )
        .order_by(models.ScheduleExecutionLog.created_at.desc())
        .first()
    )


def _create_alert(
    db: Session,
    *,
    rule: models.PlanningAlertRule,
    state: models.ScheduleExecutionState,
    recipient_id: int,
    title: str,
    task_id: Optional[int],
    message: str,
    occurrence_key: str,
) -> bool:
    deduplication_key = (
        f"OPERATIONAL:{rule.code}:{state.id}:{occurrence_key}:{recipient_id}"
    )
    exists = (
        db.query(models.PlanningNotification.id)
        .filter(
            models.PlanningNotification.deduplication_key
            == deduplication_key
        )
        .first()
    )
    if exists:
        return False
    try:
        with db.begin_nested():
            db.add(
                models.PlanningNotification(
                    user_id=recipient_id,
                    task_id=task_id,
                    source_type=state.source_type,
                    source_id=state.source_id,
                    notification_type=f"OPERATIONAL_{rule.code}",
                    title=rule.label,
                    message=f"{title} · {message}",
                    deduplication_key=deduplication_key,
                )
            )
            db.flush()
    except IntegrityError:
        return False
    return True


def evaluate_operational_alerts(
    db: Session,
    *,
    now: Optional[datetime] = None,
) -> int:
    current_time = now or utcnow()
    rules = {
        rule.code: rule
        for rule in db.query(models.PlanningAlertRule)
        .filter(models.PlanningAlertRule.is_active == True)  # noqa: E712
        .all()
        if rule.code in ALERT_RULE_CODES
    }
    if not rules:
        return 0

    states = (
        db.query(models.ScheduleExecutionState)
        .filter(
            models.ScheduleExecutionState.status.in_(
                ["IN_PROGRESS", "PAUSED", "BLOCKED"]
            )
        )
        .all()
    )
    created = 0
    for state in states:
        title, task_id, planned_minutes = _source_snapshot(db, state)

        if state.status == "BLOCKED" and "BLOCKED" in rules:
            rule = rules["BLOCKED"]
            log = _latest_log(db, state.id, "BLOCK")
            occurrence = str(log.id if log else state.updated_at.timestamp())
            reason = state.last_reason_label or state.last_reason or "Motif non précisé"
            for recipient_id in _recipient_ids(
                db, rule, state.assigned_user_id
            ):
                created += int(_create_alert(
                    db,
                    rule=rule,
                    state=state,
                    recipient_id=recipient_id,
                    title=title,
                    task_id=task_id,
                    message=f"Blocage signalé : {reason}.",
                    occurrence_key=occurrence,
                ))

        if state.status == "PAUSED" and "PAUSE_TOO_LONG" in rules:
            rule = rules["PAUSE_TOO_LONG"]
            log = _latest_log(db, state.id, "PAUSE")
            if log:
                paused_minutes = max(
                    0,
                    int(
                        (current_time - log.created_at).total_seconds()
                        // 60
                    ),
                )
                if paused_minutes >= rule.threshold_minutes:
                    for recipient_id in _recipient_ids(
                        db, rule, state.assigned_user_id
                    ):
                        created += int(_create_alert(
                            db,
                            rule=rule,
                            state=state,
                            recipient_id=recipient_id,
                            title=title,
                            task_id=task_id,
                            message=(
                                f"En pause depuis {paused_minutes} min "
                                f"(seuil {rule.threshold_minutes} min)."
                            ),
                            occurrence_key=str(log.id),
                        ))

        if state.status == "IN_PROGRESS" and "DURATION_OVERRUN" in rules:
            rule = rules["DURATION_OVERRUN"]
            elapsed = _elapsed_minutes(state, current_time)
            alert_at = planned_minutes + rule.threshold_minutes
            if elapsed >= alert_at:
                occurrence = (
                    state.started_at.isoformat()
                    if state.started_at
                    else str(state.id)
                )
                for recipient_id in _recipient_ids(
                    db, rule, state.assigned_user_id
                ):
                    created += int(_create_alert(
                        db,
                        rule=rule,
                        state=state,
                        recipient_id=recipient_id,
                        title=title,
                        task_id=task_id,
                        message=(
                            f"{elapsed} min réalisées pour {planned_minutes} "
                            f"min prévues."
                        ),
                        occurrence_key=occurrence,
                    ))
    return created

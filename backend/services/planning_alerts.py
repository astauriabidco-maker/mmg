from datetime import datetime, timedelta
from html import escape
from threading import Thread
from typing import Optional
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .. import models
from ..core.events import _send_smtp_email
from ..core.security import roles_have_permission
from ..core.time import utcnow


ALERT_RULE_CODES = {"BLOCKED", "PAUSE_TOO_LONG", "DURATION_OVERRUN"}
RECIPIENT_MODES = {"RESPONSIBLE", "MANAGERS", "BOTH"}
INCIDENT_STATUSES = {"OPEN", "ACKNOWLEDGED", "RESOLVED"}
INCIDENT_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
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
        "severity": rule.severity,
        "escalation_minutes": rule.escalation_minutes,
        "notify_pwa": rule.notify_pwa,
        "notify_email": rule.notify_email,
        "is_active": rule.is_active,
        "updated_at": rule.updated_at,
    }


def _display_user(user: Optional[models.User]) -> Optional[str]:
    if not user:
        return None
    full_name = " ".join(
        value for value in (user.first_name, user.last_name) if value
    ).strip()
    return full_name or user.username


def serialize_incident(
    incident: models.PlanningIncident,
    *,
    include_history: bool = False,
) -> dict:
    result = {
        "id": incident.id,
        "reference": incident.reference,
        "alert_code": incident.alert_code,
        "severity": incident.severity,
        "status": incident.status,
        "source_type": incident.source_type,
        "source_id": incident.source_id,
        "source_url": incident.source_url,
        "task_id": incident.task_id,
        "title": incident.title,
        "message": incident.message,
        "responsible_user_id": incident.responsible_user_id,
        "responsible_name": _display_user(incident.responsible_user),
        "assigned_manager_user_id": incident.assigned_manager_user_id,
        "assigned_manager_name": _display_user(incident.assigned_manager),
        "triggered_at": incident.triggered_at,
        "acknowledged_at": incident.acknowledged_at,
        "resolved_at": incident.resolved_at,
        "resolution_note": incident.resolution_note,
        "escalation_level": incident.escalation_level,
        "escalated_at": incident.escalated_at,
        "next_escalation_at": incident.next_escalation_at,
        "last_activity_at": incident.last_activity_at,
    }
    if include_history:
        result["history"] = [
            {
                "id": entry.id,
                "action": entry.action,
                "previous_status": entry.previous_status,
                "current_status": entry.current_status,
                "actor_user_id": entry.actor_user_id,
                "actor_name": entry.actor_name,
                "comment": entry.comment,
                "changes": entry.changes or {},
                "created_at": entry.created_at,
            }
            for entry in incident.history
        ]
    return result


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


def manager_ids(db: Session) -> set[int]:
    return _manager_ids(db)


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


def _source_url(state: models.ScheduleExecutionState) -> Optional[str]:
    return {
        "CALENDAR_TASK": "/manager?view=schedule",
        "CRM_ACTIVITY": "/manager?view=crm",
        "CRM_MILESTONE": "/manager?view=crm",
        "CRM_REMINDER": "/manager?view=crm",
        "MEASURE_MISSION": f"/measure-missions/{state.source_id}",
        "WORKSHOP": "/manager?view=orders",
        "DELIVERY": "/manager?view=logistics",
    }.get(state.source_type)


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
        elapsed += max(0, int((now - state.active_since).total_seconds() // 60))
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


def add_incident_history(
    db: Session,
    incident: models.PlanningIncident,
    action: str,
    *,
    actor_user_id: Optional[int] = None,
    actor_name: str = "Système",
    previous_status: Optional[str] = None,
    comment: Optional[str] = None,
    changes: Optional[dict] = None,
) -> None:
    incident.last_activity_at = utcnow()
    db.add(
        models.PlanningIncidentHistory(
            incident_id=incident.id,
            action=action,
            previous_status=previous_status,
            current_status=incident.status,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            comment=comment,
            changes=changes or {},
        )
    )


def _get_or_create_incident(
    db: Session,
    *,
    rule: models.PlanningAlertRule,
    state: models.ScheduleExecutionState,
    title: str,
    task_id: Optional[int],
    message: str,
    occurrence_key: str,
    now: datetime,
) -> tuple[models.PlanningIncident, bool]:
    incident_key = f"OPERATIONAL:{rule.code}:{state.id}:{occurrence_key}"
    incident = (
        db.query(models.PlanningIncident)
        .filter(models.PlanningIncident.incident_key == incident_key)
        .first()
    )
    if incident:
        return incident, False
    incident = models.PlanningIncident(
        reference=f"INC-{now.strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}",
        incident_key=incident_key,
        alert_code=rule.code,
        severity=rule.severity,
        status="OPEN",
        source_type=state.source_type,
        source_id=state.source_id,
        source_url=_source_url(state),
        execution_state_id=state.id,
        task_id=task_id,
        title=title,
        message=message,
        responsible_user_id=state.assigned_user_id,
        triggered_at=now,
        next_escalation_at=(
            now + timedelta(minutes=rule.escalation_minutes)
            if rule.escalation_minutes > 0
            else now
        ),
        last_activity_at=now,
    )
    try:
        with db.begin_nested():
            db.add(incident)
            db.flush()
            add_incident_history(
                db,
                incident,
                "CREATED",
                comment=message,
                changes={"severity": rule.severity, "alert_code": rule.code},
            )
            db.flush()
    except IntegrityError:
        incident = (
            db.query(models.PlanningIncident)
            .filter(models.PlanningIncident.incident_key == incident_key)
            .one()
        )
        return incident, False
    return incident, True


def _create_notification(
    db: Session,
    *,
    incident: models.PlanningIncident,
    rule: models.PlanningAlertRule,
    recipient_id: int,
    occurrence_key: str,
    escalated: bool = False,
) -> bool:
    if escalated and rule.notify_pwa:
        notification_type = "INCIDENT_ESCALATED"
    elif not escalated and incident.severity == "CRITICAL" and rule.notify_pwa:
        notification_type = "INCIDENT_CRITICAL"
    else:
        notification_type = (
            "OPERATIONAL_ESCALATED"
            if escalated
            else f"OPERATIONAL_{rule.code}"
        )
    deduplication_key = (
        f"{notification_type}:{incident.id}:{occurrence_key}:{recipient_id}"
    )
    if db.query(models.PlanningNotification.id).filter(
        models.PlanningNotification.deduplication_key == deduplication_key
    ).first():
        return False
    try:
        with db.begin_nested():
            db.add(
                models.PlanningNotification(
                    user_id=recipient_id,
                    task_id=incident.task_id,
                    source_type=incident.source_type,
                    source_id=incident.source_id,
                    incident_id=incident.id,
                    notification_type=notification_type,
                    title=(
                        f"Incident non pris en charge · {rule.label}"
                        if escalated
                        else rule.label
                    ),
                    message=f"{incident.title} · {incident.message}",
                    deduplication_key=deduplication_key,
                )
            )
            db.flush()
    except IntegrityError:
        return False
    return True


def _send_incident_email(
    db: Session,
    incident: models.PlanningIncident,
    recipient_ids: set[int],
    *,
    escalated: bool,
) -> None:
    users = (
        db.query(models.User)
        .filter(models.User.id.in_(recipient_ids), models.User.email.isnot(None))
        .all()
        if recipient_ids
        else []
    )
    subject = (
        f"[MMG] Incident non pris en charge {incident.reference}"
        if escalated
        else f"[MMG] Incident critique {incident.reference}"
    )
    text_body = (
        f"{incident.title}\n{incident.message or ''}\n"
        f"Criticité : {incident.severity}\n"
        f"Référence : {incident.reference}"
    )
    html_body = (
        f"<h2>{escape(incident.title)}</h2>"
        f"<p>{escape(incident.message or '')}</p>"
        f"<p><strong>Criticité :</strong> {escape(incident.severity)}<br>"
        f"<strong>Référence :</strong> {escape(incident.reference)}</p>"
    )
    email_addresses = [user.email for user in users if user.email]

    def deliver() -> None:
        for email_address in email_addresses:
            try:
                _send_smtp_email(
                    email_address,
                    subject,
                    text_body,
                    html_body,
                )
            except Exception:
                # L'incident reste exploitable même si le transport SMTP échoue.
                continue

    if email_addresses:
        Thread(target=deliver, daemon=True).start()


def evaluate_incident_escalations(
    db: Session,
    *,
    now: Optional[datetime] = None,
) -> int:
    current_time = now or utcnow()
    incidents = (
        db.query(models.PlanningIncident)
        .filter(
            models.PlanningIncident.status == "OPEN",
            models.PlanningIncident.next_escalation_at.isnot(None),
            models.PlanningIncident.next_escalation_at <= current_time,
        )
        .all()
    )
    escalated_count = 0
    rules = {
        rule.code: rule
        for rule in db.query(models.PlanningAlertRule).all()
    }
    for incident in incidents:
        rule = rules.get(incident.alert_code)
        if not rule:
            continue
        incident.escalation_level = int(incident.escalation_level or 0) + 1
        incident.escalated_at = current_time
        incident.next_escalation_at = None
        add_incident_history(
            db,
            incident,
            "ESCALATED",
            comment="Aucune prise en charge dans le délai configuré.",
            changes={"level": incident.escalation_level},
        )
        recipients = _manager_ids(db)
        if incident.responsible_user_id:
            recipients.add(incident.responsible_user_id)
        for recipient_id in recipients:
            _create_notification(
                db,
                incident=incident,
                rule=rule,
                recipient_id=recipient_id,
                occurrence_key=str(incident.escalation_level),
                escalated=True,
            )
        if rule.notify_email:
            _send_incident_email(
                db,
                incident,
                recipients,
                escalated=True,
            )
        escalated_count += 1
    return escalated_count


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
    created_notifications = 0
    states = (
        db.query(models.ScheduleExecutionState)
        .filter(
            models.ScheduleExecutionState.status.in_(
                ["IN_PROGRESS", "PAUSED", "BLOCKED"]
            )
        )
        .all()
    )
    for state in states:
        title, task_id, planned_minutes = _source_snapshot(db, state)
        candidates = []
        if state.status == "BLOCKED" and "BLOCKED" in rules:
            log = _latest_log(db, state.id, "BLOCK")
            candidates.append((
                rules["BLOCKED"],
                str(log.id if log else state.updated_at.timestamp()),
                f"Blocage signalé : {state.last_reason_label or state.last_reason or 'Motif non précisé'}.",
            ))
        if state.status == "PAUSED" and "PAUSE_TOO_LONG" in rules:
            rule = rules["PAUSE_TOO_LONG"]
            log = _latest_log(db, state.id, "PAUSE")
            if log:
                paused_minutes = max(
                    0,
                    int((current_time - log.created_at).total_seconds() // 60),
                )
                if paused_minutes >= rule.threshold_minutes:
                    candidates.append((
                        rule,
                        str(log.id),
                        f"En pause depuis {paused_minutes} min (seuil {rule.threshold_minutes} min).",
                    ))
        if state.status == "IN_PROGRESS" and "DURATION_OVERRUN" in rules:
            rule = rules["DURATION_OVERRUN"]
            elapsed = _elapsed_minutes(state, current_time)
            if elapsed >= planned_minutes + rule.threshold_minutes:
                candidates.append((
                    rule,
                    state.started_at.isoformat() if state.started_at else str(state.id),
                    f"{elapsed} min réalisées pour {planned_minutes} min prévues.",
                ))

        for rule, occurrence, message in candidates:
            incident, incident_created = _get_or_create_incident(
                db,
                rule=rule,
                state=state,
                title=title,
                task_id=task_id,
                message=message,
                occurrence_key=occurrence,
                now=current_time,
            )
            recipients = _recipient_ids(db, rule, state.assigned_user_id)
            for recipient_id in recipients:
                created_notifications += int(_create_notification(
                    db,
                    incident=incident,
                    rule=rule,
                    recipient_id=recipient_id,
                    occurrence_key=occurrence,
                ))
            if incident_created and incident.severity == "CRITICAL" and rule.notify_email:
                _send_incident_email(
                    db,
                    incident,
                    recipients,
                    escalated=False,
                )
    evaluate_incident_escalations(db, now=current_time)
    return created_notifications


def auto_resolve_incidents(
    db: Session,
    *,
    source_type: str,
    source_id: int,
    action: str,
    actor_user_id: Optional[int],
    actor_name: str,
) -> int:
    query = db.query(models.PlanningIncident).filter(
        models.PlanningIncident.source_type == source_type,
        models.PlanningIncident.source_id == source_id,
        models.PlanningIncident.status.in_(["OPEN", "ACKNOWLEDGED"]),
    )
    if action == "START":
        query = query.filter(
            models.PlanningIncident.alert_code.in_(["BLOCKED", "PAUSE_TOO_LONG"])
        )
    elif action != "COMPLETE":
        return 0
    incidents = query.all()
    now = utcnow()
    for incident in incidents:
        previous_status = incident.status
        incident.status = "RESOLVED"
        incident.resolved_at = now
        incident.resolved_by_user_id = actor_user_id
        incident.resolution_note = (
            "Résolution automatique après reprise de la tâche."
            if action == "START"
            else "Résolution automatique après fin de la tâche."
        )
        incident.next_escalation_at = None
        add_incident_history(
            db,
            incident,
            "AUTO_RESOLVED",
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            previous_status=previous_status,
            comment=incident.resolution_note,
            changes={"execution_action": action},
        )
    return len(incidents)

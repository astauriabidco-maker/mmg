from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..core.security import (
    require_permissions,
    roles_have_permission,
)
from ..core.time import utcnow
from ..database import get_db
from ..services.planning_alerts import (
    INCIDENT_SEVERITIES,
    RECIPIENT_MODES,
    add_incident_history,
    auto_resolve_incidents,
    evaluate_operational_alerts,
    serialize_alert_rule,
    serialize_incident,
)
from ..services.schedule_intelligence import calculate_capacity, suggest_assignments


router = APIRouter(
    prefix="/v2/schedule",
    tags=["planning-agenda"],
)

EDITABLE_SOURCES = {
    "CALENDAR_TASK",
    "CRM_ACTIVITY",
    "CRM_MILESTONE",
    "CRM_REMINDER",
    "MEASURE_MISSION",
    "WORKSHOP",
    "DELIVERY",
}
TASK_CATEGORIES = {"TASK", "ORDER", "MEETING", "INSTALLATION"}
TASK_STATUSES = {
    "TODO",
    "IN_PROGRESS",
    "PAUSED",
    "BLOCKED",
    "DONE",
    "CANCELLED",
}
EXECUTION_ACTIONS = {"START", "PAUSE", "BLOCK", "COMPLETE"}
EXECUTION_TRANSITIONS = {
    "START": {"TODO", "PAUSED", "BLOCKED"},
    "PAUSE": {"IN_PROGRESS"},
    "BLOCK": {"TODO", "IN_PROGRESS", "PAUSED"},
    "COMPLETE": {"IN_PROGRESS", "PAUSED", "BLOCKED"},
}
TASK_PRIORITIES = {"LOW", "NORMAL", "HIGH", "URGENT"}
COMPLETED_STATUSES = {
    "CANCELLED",
    "COMPLETED",
    "DELIVERED",
    "DONE",
    "RESOLVED",
    "ANNULE",
    "ANNULÉ",
    "TERMINE",
    "TERMINÉ",
}
DEFAULT_SOURCE_MINUTES = {
    "CALENDAR_TASK": 60,
    "CRM_ACTIVITY": 30,
    "CRM_MILESTONE": 45,
    "CRM_REMINDER": 20,
    "MEASURE_MISSION": 120,
    "WORKSHOP": 90,
    "DELIVERY": 240,
}
PARIS_TIMEZONE = ZoneInfo("Europe/Paris")
DEFAULT_WORK_SCHEDULE = {
    str(weekday): [["09:00", "12:30"], ["13:30", "17:00"]]
    for weekday in range(5)
}
ABSENCE_TYPES = {
    "LEAVE",
    "RTT",
    "SICK",
    "TRAINING",
    "UNAVAILABLE",
}


def _naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class CalendarTaskCreate(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    description: Optional[str] = Field(default=None, max_length=4000)
    category: str = "TASK"
    priority: str = "NORMAL"
    start_at: datetime
    end_at: Optional[datetime] = None
    assigned_user_id: Optional[int] = None
    client_id: Optional[int] = None
    opportunity_id: Optional[int] = None
    sale_order_id: Optional[int] = None
    location_label: Optional[str] = Field(default=None, max_length=255)
    location_address: Optional[str] = Field(default=None, max_length=1000)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    workload_minutes: Optional[int] = Field(default=None, ge=0)
    required_headcount: int = Field(default=1, ge=1, le=20)
    travel_minutes_before: int = Field(default=0, ge=0, le=480)
    travel_minutes_after: int = Field(default=0, ge=0, le=480)
    buffer_minutes_before: int = Field(default=0, ge=0, le=240)
    buffer_minutes_after: int = Field(default=0, ge=0, le=240)
    skill_requirements: list[schemas.CalendarTaskSkillRequirementBase] = Field(
        default_factory=list
    )
    resource_assignments: list[
        schemas.CalendarTaskResourceAssignmentBase
    ] = Field(default_factory=list)
    allow_conflict: bool = False

    @model_validator(mode="after")
    def validate_values(self):
        self.category = self.category.upper()
        self.priority = self.priority.upper()
        self.start_at = _naive_utc(self.start_at)
        self.end_at = _naive_utc(self.end_at)
        if self.category not in TASK_CATEGORIES:
            raise ValueError("Catégorie de planning invalide")
        if self.priority not in TASK_PRIORITIES:
            raise ValueError("Priorité de planning invalide")
        if self.end_at and self.end_at <= self.start_at:
            raise ValueError("La fin doit être postérieure au début")
        return self


class ScheduleEventUpdate(BaseModel):
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    assigned_user_id: Optional[int] = None
    status: Optional[str] = None
    change_reason: Optional[str] = Field(default=None, max_length=1000)
    source_screen: Optional[str] = Field(default="PLANNING", max_length=120)
    allow_conflict: bool = False

    @model_validator(mode="after")
    def validate_values(self):
        self.start_at = _naive_utc(self.start_at)
        self.end_at = _naive_utc(self.end_at)
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValueError("La fin doit être postérieure au début")
        return self


class ScheduleExecutionTransition(BaseModel):
    action: str
    reason_code: Optional[str] = Field(default=None, max_length=80)
    reason: Optional[str] = Field(default=None, max_length=1000)
    note: Optional[str] = Field(default=None, max_length=4000)
    time_spent_minutes: Optional[int] = Field(default=None, ge=0, le=100000)
    assigned_user_id: Optional[int] = None
    source_screen: str = Field(default="PLANNING_EXECUTION", max_length=120)

    @model_validator(mode="after")
    def validate_transition(self):
        self.action = self.action.strip().upper()
        self.reason_code = (self.reason_code or "").strip().upper() or None
        self.reason = (self.reason or "").strip() or None
        self.note = (self.note or "").strip() or None
        if self.action not in EXECUTION_ACTIONS:
            raise ValueError("Action d'exécution invalide")
        return self


class PlanningExecutionReasonCreate(BaseModel):
    action: str
    code: str = Field(min_length=2, max_length=80)
    label: str = Field(min_length=2, max_length=160)
    description: Optional[str] = Field(default=None, max_length=1000)
    requires_comment: bool = False
    sort_order: int = Field(default=100, ge=0, le=10000)
    is_active: bool = True

    @model_validator(mode="after")
    def normalize_values(self):
        self.action = self.action.strip().upper()
        self.code = self.code.strip().upper().replace(" ", "_")
        self.label = self.label.strip()
        self.description = (self.description or "").strip() or None
        if self.action not in {"PAUSE", "BLOCK"}:
            raise ValueError("Le motif doit concerner une pause ou un blocage")
        return self


class PlanningExecutionReasonUpdate(BaseModel):
    label: Optional[str] = Field(default=None, min_length=2, max_length=160)
    description: Optional[str] = Field(default=None, max_length=1000)
    requires_comment: Optional[bool] = None
    sort_order: Optional[int] = Field(default=None, ge=0, le=10000)
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def normalize_values(self):
        if self.label is not None:
            self.label = self.label.strip()
        if self.description is not None:
            self.description = self.description.strip() or None
        return self


class PlanningAlertRuleUpdate(BaseModel):
    threshold_minutes: Optional[int] = Field(default=None, ge=0, le=10080)
    recipient_mode: Optional[str] = None
    severity: Optional[str] = None
    escalation_minutes: Optional[int] = Field(default=None, ge=1, le=10080)
    notify_pwa: Optional[bool] = None
    notify_email: Optional[bool] = None
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def normalize_values(self):
        if self.recipient_mode is not None:
            self.recipient_mode = self.recipient_mode.strip().upper()
            if self.recipient_mode not in RECIPIENT_MODES:
                raise ValueError("Destinataires d’alerte invalides")
        if self.severity is not None:
            self.severity = self.severity.strip().upper()
            if self.severity not in INCIDENT_SEVERITIES:
                raise ValueError("Criticité d’incident invalide")
        return self


class PlanningIncidentAcknowledge(BaseModel):
    comment: Optional[str] = Field(default=None, max_length=2000)
    assigned_manager_user_id: Optional[int] = None


class PlanningIncidentReassign(BaseModel):
    assigned_manager_user_id: Optional[int] = None
    responsible_user_id: Optional[int] = None
    comment: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_assignment(self):
        if (
            self.assigned_manager_user_id is None
            and self.responsible_user_id is None
        ):
            raise ValueError("Sélectionnez un responsable ou un manager")
        return self


class PlanningIncidentComment(BaseModel):
    comment: str = Field(min_length=2, max_length=4000)


class PlanningIncidentResolve(BaseModel):
    comment: str = Field(min_length=2, max_length=4000)


class WorkScheduleUpdate(BaseModel):
    work_schedule: dict[str, list[list[str]]]

    @model_validator(mode="after")
    def validate_schedule(self):
        self.work_schedule = _validated_work_schedule(self.work_schedule)
        return self


class UserAbsenceCreate(BaseModel):
    start_at: datetime
    end_at: datetime
    absence_type: str = "LEAVE"
    reason: Optional[str] = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_absence(self):
        self.start_at = _naive_utc(self.start_at)
        self.end_at = _naive_utc(self.end_at)
        self.absence_type = self.absence_type.upper()
        if self.end_at <= self.start_at:
            raise ValueError("La fin doit être postérieure au début")
        if self.absence_type not in ABSENCE_TYPES:
            raise ValueError("Type d'absence invalide")
        return self


class PlanningSuggestionRequest(BaseModel):
    title: str = Field(default="Action à planifier", min_length=2, max_length=180)
    duration_minutes: int = Field(default=60, ge=15, le=1440)
    window_start: datetime
    window_end: datetime
    required_skill_ids: list[int] = Field(default_factory=list)
    required_resource_ids: list[int] = Field(default_factory=list)
    location_label: Optional[str] = Field(default=None, max_length=255)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    travel_margin_minutes: int = Field(default=15, ge=0, le=240)
    step_minutes: int = Field(default=30, ge=15, le=240)
    limit: int = Field(default=8, ge=1, le=30)

    @model_validator(mode="after")
    def validate_window(self):
        self.window_start = _naive_utc(self.window_start)
        self.window_end = _naive_utc(self.window_end)
        if self.window_end <= self.window_start:
            raise ValueError("La fin de recherche doit être postérieure au début")
        if self.window_end - self.window_start > timedelta(days=31):
            raise ValueError("La recherche est limitée à 31 jours")
        return self


class UserSkillsUpdate(BaseModel):
    skills: list[schemas.UserPlanningSkillBase] = Field(default_factory=list)


class ResourceMembersUpdate(BaseModel):
    members: list[schemas.PlanningResourceMemberBase] = Field(default_factory=list)


def _display_user(user: Optional[models.User]) -> Optional[str]:
    if not user:
        return None
    full_name = " ".join(
        value for value in (user.first_name, user.last_name) if value
    ).strip()
    return full_name or user.username


def _enum_value(value):
    return getattr(value, "value", value)


def _default_end(start_at: datetime, end_at: Optional[datetime], minutes: int = 60):
    return end_at or start_at + timedelta(minutes=minutes)


def _event(
    source_type: str,
    source_id: int,
    category: str,
    title: str,
    start_at: Optional[datetime],
    *,
    end_at: Optional[datetime] = None,
    status: str = "TODO",
    owner_id: Optional[int] = None,
    owner_name: Optional[str] = None,
    reference: Optional[str] = None,
    client_name: Optional[str] = None,
    location: Optional[str] = None,
    priority: str = "NORMAL",
    source_view: Optional[str] = None,
    source_url: Optional[str] = None,
    subtitle: Optional[str] = None,
    editable: Optional[bool] = None,
    **details: Any,
):
    event = {
        "id": f"{source_type}:{source_id}",
        "source_type": source_type,
        "source_id": source_id,
        "category": category,
        "title": title,
        "subtitle": subtitle,
        "start_at": start_at,
        "end_at": end_at,
        "status": _enum_value(status),
        "owner_id": owner_id,
        "owner_name": owner_name,
        "reference": reference,
        "client_name": client_name,
        "location": location,
        "priority": priority,
        "editable": source_type in EDITABLE_SOURCES if editable is None else editable,
        "source_view": source_view,
        "source_url": source_url,
        "unscheduled": start_at is None,
    }
    event.update(details)
    return event


def _serialize_event(event: dict) -> dict:
    """Expose the project's naive UTC datetimes as explicit UTC timestamps."""
    serialized = dict(event)
    for field in ("start_at", "end_at"):
        value = serialized.get(field)
        if isinstance(value, datetime):
            serialized[field] = f"{_naive_utc(value).isoformat()}Z"
    return serialized


def _serialize_alert(alert: dict) -> dict:
    serialized = dict(alert)
    for field in ("start_at", "end_at"):
        value = serialized.get(field)
        if isinstance(value, datetime):
            serialized[field] = f"{_naive_utc(value).isoformat()}Z"
    return serialized


def _status_value(status) -> str:
    return str(_enum_value(status) or "").upper()


def _is_completed(status) -> bool:
    return _status_value(status) in COMPLETED_STATUSES


def _event_end(event: dict) -> Optional[datetime]:
    start_at = event.get("start_at")
    if not start_at:
        return None
    return event.get("end_at") or start_at + timedelta(
        minutes=DEFAULT_SOURCE_MINUTES.get(event.get("source_type"), 60)
    )


def _events_overlap(first: dict, second: dict) -> bool:
    first_start = first.get("start_at")
    second_start = second.get("start_at")
    first_end = _event_end(first)
    second_end = _event_end(second)
    return bool(
        first_start
        and second_start
        and first_end
        and second_end
        and first_start < second_end
        and second_start < first_end
    )


def _parse_work_time(value: str) -> tuple[int, int]:
    try:
        hours, minutes = (int(part) for part in value.split(":", 1))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"Horaire invalide : {value}") from exc
    if not 0 <= hours <= 23 or not 0 <= minutes <= 59:
        raise ValueError(f"Horaire invalide : {value}")
    return hours, minutes


def _validated_work_schedule(raw_schedule: Optional[dict]) -> dict:
    if not raw_schedule:
        return {day: [list(interval) for interval in intervals] for day, intervals in DEFAULT_WORK_SCHEDULE.items()}
    normalized = {}
    weekly_minutes = 0
    for day_key, raw_intervals in raw_schedule.items():
        try:
            weekday = int(day_key)
        except (TypeError, ValueError) as exc:
            raise ValueError("Le jour de travail doit être compris entre 0 et 6") from exc
        if weekday < 0 or weekday > 6:
            raise ValueError("Le jour de travail doit être compris entre 0 et 6")
        intervals = []
        for raw_interval in raw_intervals or []:
            if not isinstance(raw_interval, (list, tuple)) or len(raw_interval) != 2:
                raise ValueError("Chaque plage horaire doit contenir un début et une fin")
            start_value, end_value = raw_interval
            start_hour, start_minute = _parse_work_time(start_value)
            end_hour, end_minute = _parse_work_time(end_value)
            start_total = start_hour * 60 + start_minute
            end_total = end_hour * 60 + end_minute
            if end_total <= start_total:
                raise ValueError("La fin d'une plage doit être postérieure à son début")
            intervals.append((start_total, end_total, f"{start_hour:02d}:{start_minute:02d}", f"{end_hour:02d}:{end_minute:02d}"))
        intervals.sort()
        for index, interval in enumerate(intervals):
            if index and interval[0] < intervals[index - 1][1]:
                raise ValueError("Deux plages de travail ne peuvent pas se chevaucher")
            weekly_minutes += interval[1] - interval[0]
        if intervals:
            normalized[str(weekday)] = [
                [interval[2], interval[3]] for interval in intervals
            ]
    if weekly_minutes <= 0 or weekly_minutes > 60 * 60:
        raise ValueError("La durée hebdomadaire doit être comprise entre 0 et 60 heures")
    return normalized


def _schedule_weekly_hours(work_schedule: dict) -> float:
    total_minutes = 0
    for intervals in work_schedule.values():
        for start_value, end_value in intervals:
            start_hour, start_minute = _parse_work_time(start_value)
            end_hour, end_minute = _parse_work_time(end_value)
            total_minutes += (
                end_hour * 60 + end_minute - start_hour * 60 - start_minute
            )
    return round(total_minutes / 60, 2)


def _user_work_schedule(user: models.User) -> dict:
    try:
        return _validated_work_schedule(user.work_schedule)
    except ValueError:
        return _validated_work_schedule(None)


def _local_schedule_interval(
    local_day,
    start_value: str,
    end_value: str,
) -> tuple[datetime, datetime]:
    start_hour, start_minute = _parse_work_time(start_value)
    end_hour, end_minute = _parse_work_time(end_value)
    local_start = datetime(
        local_day.year,
        local_day.month,
        local_day.day,
        start_hour,
        start_minute,
        tzinfo=PARIS_TIMEZONE,
    )
    local_end = datetime(
        local_day.year,
        local_day.month,
        local_day.day,
        end_hour,
        end_minute,
        tzinfo=PARIS_TIMEZONE,
    )
    return (
        local_start.astimezone(timezone.utc).replace(tzinfo=None),
        local_end.astimezone(timezone.utc).replace(tzinfo=None),
    )


def _merge_intervals(
    intervals: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    merged = []
    for start_at, end_at in sorted(intervals):
        if not merged or start_at > merged[-1][1]:
            merged.append([start_at, end_at])
        else:
            merged[-1][1] = max(merged[-1][1], end_at)
    return [tuple(interval) for interval in merged]


def _working_capacity_hours(
    user: models.User,
    start_at: datetime,
    end_at: datetime,
    absences: list[models.UserAbsence],
) -> tuple[float, float]:
    """Return effective capacity and absence hours for an individual."""
    schedule = _user_work_schedule(user)
    local_start_date = start_at.replace(tzinfo=timezone.utc).astimezone(PARIS_TIMEZONE).date()
    local_end_date = (
        end_at - timedelta(microseconds=1)
    ).replace(tzinfo=timezone.utc).astimezone(PARIS_TIMEZONE).date()
    work_intervals = []
    current_day = local_start_date
    while current_day <= local_end_date:
        for interval_start, interval_end in schedule.get(str(current_day.weekday()), []):
            work_start, work_end = _local_schedule_interval(
                current_day,
                interval_start,
                interval_end,
            )
            clipped_start = max(start_at, work_start)
            clipped_end = min(end_at, work_end)
            if clipped_start < clipped_end:
                work_intervals.append((clipped_start, clipped_end))
        current_day += timedelta(days=1)

    absence_intervals = _merge_intervals([
        (max(start_at, absence.start_at), min(end_at, absence.end_at))
        for absence in absences
        if absence.status == "APPROVED"
        and absence.start_at < end_at
        and absence.end_at > start_at
    ])
    gross_seconds = sum(
        (work_end - work_start).total_seconds()
        for work_start, work_end in work_intervals
    )
    absence_seconds = 0.0
    for work_start, work_end in work_intervals:
        for absence_start, absence_end in absence_intervals:
            overlap_start = max(work_start, absence_start)
            overlap_end = min(work_end, absence_end)
            if overlap_start < overlap_end:
                absence_seconds += (overlap_end - overlap_start).total_seconds()
    return (
        round(max(gross_seconds - absence_seconds, 0) / 3600, 2),
        round(absence_seconds / 3600, 2),
    )


def _planned_hours(event: dict, period_start: datetime, period_end: datetime) -> float:
    start_at = event.get("start_at")
    end_at = _event_end(event)
    if not start_at or not end_at:
        return 0.0
    clipped_start = max(start_at, period_start)
    clipped_end = min(end_at, period_end)
    if clipped_start >= clipped_end:
        return 0.0
    return (clipped_end - clipped_start).total_seconds() / 3600


def _is_overdue(event: dict, now: datetime) -> bool:
    due_at = _event_end(event) or event.get("start_at")
    return bool(due_at and due_at < now and not _is_completed(event.get("status")))


def _active_user(db: Session, user_id: Optional[int]) -> Optional[models.User]:
    if user_id is None:
        return None
    user = (
        db.query(models.User)
        .filter(models.User.id == user_id, models.User.is_active == True)  # noqa: E712
        .first()
    )
    if not user:
        raise HTTPException(status_code=422, detail="Responsable actif introuvable")
    return user


def _active_user_by_name(
    db: Session,
    value: Optional[str],
) -> Optional[models.User]:
    normalized = (value or "").strip().casefold()
    if not normalized:
        return None
    users = (
        db.query(models.User)
        .options(
            selectinload(models.User.planning_skills).selectinload(
                models.UserPlanningSkill.skill
            ),
            selectinload(models.User.stations),
        )
        .filter(models.User.is_active == True)  # noqa: E712
        .all()
    )
    return next(
        (
            user
            for user in users
            if normalized
            in {
                (user.username or "").casefold(),
                (_display_user(user) or "").casefold(),
            }
        ),
        None,
    )


def _overlaps(start_column, end_column, start_at: datetime, end_at: datetime):
    return and_(
        start_column < end_at,
        or_(end_column.is_(None), end_column > start_at),
    )


def _conflicts(
    db: Session,
    assigned_user_id: Optional[int],
    start_at: datetime,
    end_at: datetime,
    *,
    exclude_source: Optional[str] = None,
    exclude_id: Optional[int] = None,
):
    if not assigned_user_id:
        return []
    user = db.get(models.User, assigned_user_id)
    if not user or not user.is_active:
        return []

    candidates = []

    for task in db.query(models.CalendarTask).filter(
        models.CalendarTask.assigned_user_id == assigned_user_id,
        models.CalendarTask.status != "CANCELLED",
        models.CalendarTask.start_at < end_at,
    ).all():
        candidates.append(
            _event(
                "CALENDAR_TASK",
                task.id,
                task.category,
                task.title,
                task.start_at,
                end_at=_default_end(task.start_at, task.end_at),
                status=task.status,
                owner_id=assigned_user_id,
                owner_name=_display_user(user),
                reference=f"PLN-{task.id:05d}",
            )
        )

    for mission in db.query(models.MeasureMission).filter(
        models.MeasureMission.assigned_user_id == assigned_user_id,
        models.MeasureMission.status != models.MeasureMissionStatus.CANCELLED.value,
        models.MeasureMission.scheduled_start.is_not(None),
        models.MeasureMission.scheduled_start < end_at,
    ).all():
        candidates.append(
            _event(
                "MEASURE_MISSION",
                mission.id,
                "MEASURE",
                f"Métré {mission.reference}",
                mission.scheduled_start,
                end_at=_default_end(
                    mission.scheduled_start,
                    mission.scheduled_end,
                    120,
                ),
                status=mission.status,
                owner_id=assigned_user_id,
                owner_name=_display_user(user),
                reference=mission.reference,
            )
        )

    for activity in db.query(models.CRMActivity).filter(
        models.CRMActivity.assigned_user_id == assigned_user_id,
        models.CRMActivity.status != models.CRMActivityStatus.CANCELLED.value,
        models.CRMActivity.due_at >= start_at - timedelta(minutes=30),
        models.CRMActivity.due_at < end_at,
    ).all():
        candidates.append(
            _event(
                "CRM_ACTIVITY",
                activity.id,
                "CRM",
                activity.subject,
                activity.due_at,
                end_at=activity.due_at + timedelta(minutes=30),
                status=activity.status,
                owner_id=assigned_user_id,
                owner_name=_display_user(user),
            )
        )

    for opportunity in db.query(models.CRMOpportunity).filter(
        models.CRMOpportunity.owner_user_id == assigned_user_id,
        models.CRMOpportunity.next_milestone_at >= start_at - timedelta(minutes=45),
        models.CRMOpportunity.next_milestone_at < end_at,
        models.CRMOpportunity.stage.notin_(
            [
                models.CRMOpportunityStage.WON.value,
                models.CRMOpportunityStage.LOST.value,
            ]
        ),
    ).all():
        candidates.append(
            _event(
                "CRM_MILESTONE",
                opportunity.id,
                "CRM",
                opportunity.next_milestone or f"Suivi {opportunity.reference}",
                opportunity.next_milestone_at,
                end_at=opportunity.next_milestone_at + timedelta(minutes=45),
                status=opportunity.stage,
                owner_id=assigned_user_id,
                owner_name=_display_user(user),
                reference=opportunity.reference,
            )
        )

    for reminder in db.query(models.CRMReminderPlan).filter(
        models.CRMReminderPlan.assigned_user_id == assigned_user_id,
        models.CRMReminderPlan.status == "PENDING",
        models.CRMReminderPlan.due_at >= start_at - timedelta(minutes=20),
        models.CRMReminderPlan.due_at < end_at,
    ).all():
        candidates.append(
            _event(
                "CRM_REMINDER",
                reminder.id,
                "REMINDER",
                f"Relance {reminder.opportunity_id}",
                reminder.due_at,
                end_at=reminder.due_at + timedelta(minutes=20),
                status=reminder.status,
                owner_id=assigned_user_id,
                owner_name=_display_user(user),
            )
        )

    user_names = {
        value.casefold()
        for value in (user.username, _display_user(user))
        if value
    }
    planned_work = (
        db.query(models.Planning)
        .options(selectinload(models.Planning.order))
        .filter(
            models.Planning.status.notin_(
                [models.PlanningStatus.DONE, models.PlanningStatus.DEFECT]
            ),
            models.Planning.scheduled_start.is_not(None),
            models.Planning.scheduled_start < end_at,
        )
        .all()
    )
    for planning in planned_work:
        if (planning.assigned_to or "").strip().casefold() not in user_names:
            continue
        candidates.append(
            _event(
                "WORKSHOP",
                planning.id,
                "WORKSHOP",
                f"{planning.station} · {planning.order_reference}",
                planning.scheduled_start,
                end_at=_default_end(
                    planning.scheduled_start,
                    planning.scheduled_end,
                    90,
                ),
                status=planning.status,
                owner_id=assigned_user_id,
                owner_name=_display_user(user),
                reference=planning.order_reference,
            )
        )

    for route in db.query(models.DeliveryRoute).filter(
        models.DeliveryRoute.status != "COMPLETED",
        models.DeliveryRoute.planned_date >= start_at - timedelta(hours=4),
        models.DeliveryRoute.planned_date < end_at,
    ).all():
        if (route.driver_name or "").strip().casefold() not in user_names:
            continue
        candidates.append(
            _event(
                "DELIVERY",
                route.id,
                "DELIVERY",
                f"Tournée {route.reference}",
                route.planned_date,
                end_at=route.planned_date + timedelta(hours=4),
                status=route.status,
                owner_id=assigned_user_id,
                owner_name=_display_user(user),
                reference=route.reference,
            )
        )

    for absence in db.query(models.UserAbsence).filter(
        models.UserAbsence.user_id == assigned_user_id,
        models.UserAbsence.status == "APPROVED",
        models.UserAbsence.start_at < end_at,
        models.UserAbsence.end_at > start_at,
    ).all():
        candidates.append(
            _event(
                "USER_ABSENCE",
                absence.id,
                "ABSENCE",
                absence.reason or "Indisponibilité validée",
                absence.start_at,
                end_at=absence.end_at,
                status=absence.status,
                owner_id=assigned_user_id,
                owner_name=_display_user(user),
                reference=absence.absence_type,
                editable=False,
            )
        )

    requested = _event(
        "REQUESTED",
        0,
        "TASK",
        "Créneau demandé",
        start_at,
        end_at=end_at,
        owner_id=assigned_user_id,
    )
    return [
        event
        for event in candidates
        if not (
            event["source_type"] == exclude_source
            and event["source_id"] == exclude_id
        )
        and _events_overlap(event, requested)
    ]


def _ensure_no_conflict(
    db: Session,
    assigned_user_id: Optional[int],
    start_at: datetime,
    end_at: datetime,
    allow_conflict: bool,
    *,
    exclude_source: Optional[str] = None,
    exclude_id: Optional[int] = None,
):
    conflicts = _conflicts(
        db,
        assigned_user_id,
        start_at,
        end_at,
        exclude_source=exclude_source,
        exclude_id=exclude_id,
    )
    absence_conflicts = [
        conflict
        for conflict in conflicts
        if conflict.get("source_type") == "USER_ABSENCE"
    ]
    if absence_conflicts:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Ce responsable est indisponible sur ce créneau. "
                    "Modifiez ou supprimez d'abord l'absence validée."
                ),
                "conflicts": [
                    _serialize_event(event)
                    for event in absence_conflicts
                ],
            },
        )
    if conflicts and not allow_conflict:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Ce responsable a déjà une action sur ce créneau.",
                "conflicts": [_serialize_event(event) for event in conflicts],
            },
        )


def _has_permission(
    db: Session,
    current_user: dict,
    permission_code: str,
) -> bool:
    permissions = current_user.get("permissions") or []
    if "*" in permissions or permission_code in permissions:
        return True
    role_names = current_user.get("roles") or [current_user.get("role")]
    return roles_have_permission(
        db,
        [role for role in role_names if role],
        permission_code,
    )


def _has_edit_permission(db: Session, current_user: dict) -> bool:
    return _has_permission(db, current_user, "PLANNING_EDIT")


def _current_user_record(
    db: Session,
    current_user: dict,
) -> Optional[models.User]:
    username = (current_user.get("sub") or "").strip()
    if not username:
        return None
    return (
        db.query(models.User)
        .filter(models.User.username == username)
        .first()
    )


def _serialize_absence(absence: models.UserAbsence) -> dict:
    return {
        "id": absence.id,
        "user_id": absence.user_id,
        "start_at": f"{_naive_utc(absence.start_at).isoformat()}Z",
        "end_at": f"{_naive_utc(absence.end_at).isoformat()}Z",
        "absence_type": absence.absence_type,
        "status": absence.status,
        "reason": absence.reason,
        "created_by": absence.created_by,
        "created_at": (
            f"{_naive_utc(absence.created_at).isoformat()}Z"
            if absence.created_at
            else None
        ),
        "requested_at": (
            f"{_naive_utc(absence.requested_at).isoformat()}Z"
            if absence.requested_at
            else None
        ),
        "reviewed_by_user_id": absence.reviewed_by_user_id,
        "reviewed_at": (
            f"{_naive_utc(absence.reviewed_at).isoformat()}Z"
            if absence.reviewed_at
            else None
        ),
        "review_note": absence.review_note,
    }


def _actor_identity(
    db: Session,
    current_user: dict,
) -> tuple[Optional[int], str]:
    user = _current_user_record(db, current_user)
    return (
        user.id if user else None,
        _display_user(user) if user else current_user.get("sub") or "Système",
    )


def _record_task_change(
    db: Session,
    task: models.CalendarTask,
    current_user: dict,
    action: str,
    *,
    changes: Optional[dict] = None,
    reason: Optional[str] = None,
    source_screen: Optional[str] = "PLANNING",
) -> None:
    actor_id, actor_name = _actor_identity(db, current_user)
    db.add(
        models.PlanningChangeLog(
            task_id=task.id,
            action=action,
            changes=changes or {},
            reason=(reason or "").strip() or None,
            source_screen=source_screen,
            actor_user_id=actor_id,
            actor_name=actor_name,
        )
    )


def _notify_assignment(
    db: Session,
    task: models.CalendarTask,
    user_id: Optional[int],
    notification_type: str,
) -> None:
    if not user_id:
        return
    timestamp = utcnow().strftime("%Y%m%d%H%M%S%f")
    db.add(
        models.PlanningNotification(
            user_id=user_id,
            task_id=task.id,
            source_type="CALENDAR_TASK",
            source_id=task.id,
            notification_type=notification_type,
            title=(
                "Nouvelle affectation"
                if notification_type == "ASSIGNMENT"
                else "Planning modifié"
            ),
            message=(
                f"{task.title} · "
                f"{task.start_at.strftime('%d/%m/%Y %H:%M')}"
            ),
            deduplication_key=(
                f"{notification_type}:{task.id}:{user_id}:{timestamp}"
            ),
        )
    )


def _execution_source(
    db: Session,
    source_type: str,
    source_id: int,
) -> tuple[Any, Optional[int], str, Optional[str]]:
    source_type = source_type.upper()
    record = None
    owner_id = None
    title = f"{source_type} #{source_id}"
    source_url = None

    if source_type == "CALENDAR_TASK":
        record = db.get(models.CalendarTask, source_id)
        if record:
            owner_id = record.assigned_user_id
            title = record.title
            source_url = (
                f"/manager?view=sale-detail&id={record.sale_order_id}&from=sales"
                if record.sale_order_id
                else None
            )
    elif source_type == "CRM_ACTIVITY":
        record = db.get(models.CRMActivity, source_id)
        if record:
            owner_id = record.assigned_user_id
            title = record.subject
            source_url = "/manager?view=crm"
    elif source_type == "CRM_MILESTONE":
        record = db.get(models.CRMOpportunity, source_id)
        if record:
            owner_id = record.owner_user_id
            title = record.next_milestone or record.title
            source_url = "/manager?view=crm"
    elif source_type == "CRM_REMINDER":
        record = db.get(models.CRMReminderPlan, source_id)
        if record:
            owner_id = record.assigned_user_id
            title = f"Relance {record.opportunity_reference or record.client_name}"
            source_url = "/manager?view=crm"
    elif source_type == "MEASURE_MISSION":
        record = db.get(models.MeasureMission, source_id)
        if record:
            owner_id = record.assigned_user_id
            title = f"Métré {record.reference}"
            source_url = f"/measure-missions/{record.id}"
    elif source_type == "WORKSHOP":
        record = db.get(models.Planning, source_id)
        if record:
            owner = _active_user_by_name(db, record.assigned_to)
            owner_id = owner.id if owner else None
            title = f"{record.station} · {record.order_reference}"
            source_url = "/manager?view=orders"
    elif source_type == "DELIVERY":
        record = db.get(models.DeliveryRoute, source_id)
        if record:
            owner = _active_user_by_name(db, record.driver_name)
            owner_id = owner.id if owner else None
            title = f"Tournée {record.reference}"
            source_url = "/manager?view=logistics"
    if not record:
        raise HTTPException(status_code=404, detail="Événement de planning introuvable")
    return record, owner_id, title, source_url


def _initial_execution_status(source_type: str, record: Any) -> str:
    status_value = _status_value(getattr(record, "status", None))
    if source_type == "CALENDAR_TASK" and status_value in TASK_STATUSES:
        return status_value
    if source_type == "CRM_ACTIVITY":
        return "DONE" if status_value == "COMPLETED" else "TODO"
    if source_type == "CRM_REMINDER":
        if status_value in {"SENT", "SKIPPED"}:
            return "DONE"
        return "BLOCKED" if status_value == "FAILED" else "TODO"
    if source_type == "MEASURE_MISSION":
        if status_value in {"IN_CAPTURE", "ON_SITE"}:
            return "IN_PROGRESS"
        if status_value in {"TO_REVIEW", "VALIDATED", "QUOTED"}:
            return "DONE"
        if status_value == "CORRECTION_REQUIRED":
            return "BLOCKED"
        return "TODO"
    if source_type == "WORKSHOP":
        return {
            "PENDING": "TODO",
            "IN_PROGRESS": "IN_PROGRESS",
            "PAUSED": "PAUSED",
            "ISSUE": "BLOCKED",
            "DEFECT": "BLOCKED",
            "DONE": "DONE",
        }.get(status_value, "TODO")
    if source_type == "DELIVERY":
        return {
            "PLANNED": "TODO",
            "IN_TRANSIT": "IN_PROGRESS",
            "COMPLETED": "DONE",
        }.get(status_value, "TODO")
    return "TODO"


def _execution_elapsed_minutes(
    state: models.ScheduleExecutionState,
    now: Optional[datetime] = None,
) -> int:
    elapsed = int(state.elapsed_minutes or 0)
    if state.status == "IN_PROGRESS" and state.active_since:
        current_time = now or utcnow()
        elapsed += max(
            0,
            int((current_time - state.active_since).total_seconds() // 60),
        )
    return elapsed


def _execution_allowed_actions(status_value: str) -> list[str]:
    return [
        action
        for action, allowed_statuses in EXECUTION_TRANSITIONS.items()
        if status_value in allowed_statuses
    ]


def _resolve_execution_reason(
    db: Session,
    *,
    action: str,
    reason_code: Optional[str],
    comment: Optional[str],
) -> Optional[models.PlanningExecutionReason]:
    if action not in {"PAUSE", "BLOCK"}:
        return None
    if not reason_code:
        # Compatibility with clients deployed before the dynamic reason catalog.
        if comment:
            return None
        raise HTTPException(
            status_code=422,
            detail="Sélectionnez un motif de pause ou de blocage.",
        )
    reason = (
        db.query(models.PlanningExecutionReason)
        .filter(
            models.PlanningExecutionReason.action == action,
            models.PlanningExecutionReason.code == reason_code,
            models.PlanningExecutionReason.is_active == True,  # noqa: E712
        )
        .first()
    )
    if not reason:
        raise HTTPException(
            status_code=422,
            detail="Ce motif n’existe pas ou n’est plus actif.",
        )
    if reason.requires_comment and not comment:
        raise HTTPException(
            status_code=422,
            detail=f"Une précision est obligatoire pour « {reason.label} ».",
        )
    return reason


def _execution_payload(
    state: Optional[models.ScheduleExecutionState],
    *,
    source_type: str,
    source_id: int,
    owner_id: Optional[int],
    title: str,
    source_url: Optional[str],
    initial_status: str,
    can_execute: bool,
    can_manage: bool,
    history: Optional[list[models.ScheduleExecutionLog]] = None,
) -> dict:
    status_value = state.status if state else initial_status
    responsible_id = state.assigned_user_id if state else owner_id
    return {
        "id": state.id if state else None,
        "source_type": source_type,
        "source_id": source_id,
        "title": title,
        "source_url": source_url,
        "status": status_value,
        "assigned_user_id": responsible_id,
        "responsible_name": (
            _display_user(state.assigned_user)
            if state and state.assigned_user
            else None
        ),
        "started_at": state.started_at if state else None,
        "completed_at": state.completed_at if state else None,
        "elapsed_minutes": _execution_elapsed_minutes(state) if state else 0,
        "last_reason_code": state.last_reason_code if state else None,
        "last_reason_label": state.last_reason_label if state else None,
        "last_reason": state.last_reason if state else None,
        "last_note": state.last_note if state else None,
        "can_execute": can_execute,
        "can_manage": can_manage,
        "allowed_actions": (
            _execution_allowed_actions(status_value) if can_execute else []
        ),
        "history": [
            {
                "id": item.id,
                "action": item.action,
                "previous_status": item.previous_status,
                "current_status": item.current_status,
                "reason_code": item.reason_code,
                "reason_label": item.reason_label,
                "reason": item.reason,
                "note": item.note,
                "elapsed_minutes": item.elapsed_minutes,
                "responsible_user_id": item.responsible_user_id,
                "actor_name": item.actor_name,
                "source_screen": item.source_screen,
                "created_at": item.created_at,
            }
            for item in (history or [])
        ],
    }


def _sync_execution_source(
    db: Session,
    source_type: str,
    record: Any,
    status_value: str,
    reason: Optional[str],
) -> None:
    now = utcnow()
    if source_type == "CALENDAR_TASK":
        record.status = status_value
    elif source_type == "CRM_ACTIVITY":
        record.status = (
            models.CRMActivityStatus.COMPLETED.value
            if status_value == "DONE"
            else models.CRMActivityStatus.TODO.value
        )
        record.completed_at = now if status_value == "DONE" else None
    elif source_type == "MEASURE_MISSION":
        if status_value == "IN_PROGRESS":
            record.status = models.MeasureMissionStatus.IN_CAPTURE.value
        elif status_value == "DONE":
            record.status = models.MeasureMissionStatus.TO_REVIEW.value
        elif status_value == "BLOCKED":
            record.status = models.MeasureMissionStatus.CORRECTION_REQUIRED.value
    elif source_type == "WORKSHOP":
        record.status = {
            "TODO": models.PlanningStatus.PENDING,
            "IN_PROGRESS": models.PlanningStatus.IN_PROGRESS,
            "PAUSED": models.PlanningStatus.PAUSED,
            "BLOCKED": models.PlanningStatus.ISSUE,
            "DONE": models.PlanningStatus.DONE,
        }[status_value]
        if status_value == "BLOCKED":
            record.issue_notes = reason
    elif source_type == "DELIVERY":
        if status_value == "IN_PROGRESS":
            record.status = "IN_TRANSIT"
            for delivery_note in record.notes:
                if delivery_note.status in {"READY", "ASSIGNED"}:
                    delivery_note.status = "IN_TRANSIT"
        elif status_value == "BLOCKED":
            for delivery_note in record.notes:
                if delivery_note.status != "DELIVERED":
                    delivery_note.status = "ISSUE"
                    if reason:
                        delivery_note.delivery_notes = reason
        elif status_value == "DONE":
            record.status = "COMPLETED"
            for delivery_note in record.notes:
                if delivery_note.status in {"READY", "ASSIGNED", "IN_TRANSIT"}:
                    delivery_note.status = "DELIVERED"


def _assign_execution_source(
    source_type: str,
    record: Any,
    user: Optional[models.User],
) -> None:
    user_id = user.id if user else None
    if source_type == "CALENDAR_TASK":
        record.assigned_user_id = user_id
    elif source_type == "CRM_ACTIVITY":
        record.assigned_user_id = user_id
    elif source_type == "CRM_MILESTONE":
        record.owner_user_id = user_id
    elif source_type == "CRM_REMINDER":
        record.assigned_user_id = user_id
    elif source_type == "MEASURE_MISSION":
        record.assigned_user_id = user_id
    elif source_type == "WORKSHOP":
        record.assigned_to = user.username if user else None
    elif source_type == "DELIVERY":
        record.driver_name = _display_user(user) if user else None


def _notify_execution(
    db: Session,
    *,
    source_type: str,
    source_id: int,
    task_id: Optional[int],
    user_id: Optional[int],
    title: str,
    action: str,
    actor_name: str,
) -> None:
    if not user_id:
        return
    action_labels = {
        "START": "démarrée",
        "PAUSE": "mise en pause",
        "BLOCK": "bloquée",
        "COMPLETE": "terminée",
    }
    timestamp = utcnow().strftime("%Y%m%d%H%M%S%f")
    db.add(
        models.PlanningNotification(
            user_id=user_id,
            task_id=task_id,
            source_type=source_type,
            source_id=source_id,
            notification_type=f"EXECUTION_{action}",
            title=f"Tâche {action_labels[action]}",
            message=f"{title} · par {actor_name}",
            deduplication_key=(
                f"EXECUTION:{source_type}:{source_id}:{user_id}:{timestamp}"
            ),
        )
    )


def _sync_task_requirements(
    db: Session,
    task: models.CalendarTask,
    payload: CalendarTaskCreate,
    current_user: dict,
) -> None:
    skill_ids = [item.skill_id for item in payload.skill_requirements]
    if len(skill_ids) != len(set(skill_ids)):
        raise HTTPException(status_code=422, detail="Compétence requise en double")
    if skill_ids:
        known = {
            item.id
            for item in db.query(models.PlanningSkill)
            .filter(
                models.PlanningSkill.id.in_(skill_ids),
                models.PlanningSkill.is_active == True,  # noqa: E712
            )
            .all()
        }
        if known != set(skill_ids):
            raise HTTPException(status_code=422, detail="Compétence requise introuvable")
    for item in payload.skill_requirements:
        task.skill_requirements.append(
            models.CalendarTaskSkillRequirement(
                skill_id=item.skill_id,
                minimum_level=item.minimum_level,
                is_mandatory=item.is_mandatory,
                notes=item.notes,
            )
        )

    resource_ids = [item.resource_id for item in payload.resource_assignments]
    if len(resource_ids) != len(set(resource_ids)):
        raise HTTPException(status_code=422, detail="Ressource requise en double")
    if resource_ids:
        known = {
            item.id
            for item in db.query(models.PlanningResource)
            .filter(
                models.PlanningResource.id.in_(resource_ids),
                models.PlanningResource.is_active == True,  # noqa: E712
            )
            .all()
        }
        if known != set(resource_ids):
            raise HTTPException(status_code=422, detail="Ressource requise introuvable")
    actor_id, _ = _actor_identity(db, current_user)
    for item in payload.resource_assignments:
        task.resource_assignments.append(
            models.CalendarTaskResourceAssignment(
                resource_id=item.resource_id,
                quantity=item.quantity,
                status=item.status,
                notes=item.notes,
                assigned_by_user_id=actor_id,
            )
        )


def _serialize_skill(skill: models.PlanningSkill) -> dict:
    return {
        "id": skill.id,
        "code": skill.code,
        "name": skill.name,
        "category": skill.category,
        "description": skill.description,
        "requires_expiry": skill.requires_expiry,
        "is_active": skill.is_active,
    }


def _serialize_execution_reason(
    reason: models.PlanningExecutionReason,
) -> dict:
    return {
        "id": reason.id,
        "action": reason.action,
        "code": reason.code,
        "label": reason.label,
        "description": reason.description,
        "requires_comment": reason.requires_comment,
        "sort_order": reason.sort_order,
        "is_active": reason.is_active,
        "created_by": reason.created_by,
        "created_at": reason.created_at,
        "updated_at": reason.updated_at,
    }


def _serialize_resource(resource: models.PlanningResource) -> dict:
    return {
        "id": resource.id,
        "code": resource.code,
        "name": resource.name,
        "resource_type": resource.resource_type,
        "status": resource.status,
        "station_id": resource.station_id,
        "capacity": resource.capacity,
        "timezone": resource.timezone,
        "details": resource.details,
        "is_active": resource.is_active,
        "members": [
            {
                "id": member.id,
                "user_id": member.user_id,
                "member_role": member.member_role,
                "is_lead": member.is_lead,
            }
            for member in resource.members
        ],
    }


@router.get("/availability")
def get_team_availability(
    start_at: Optional[datetime] = None,
    end_at: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_VIEW")),
):
    start_at = _naive_utc(start_at) if start_at else utcnow() - timedelta(days=90)
    end_at = _naive_utc(end_at) if end_at else utcnow() + timedelta(days=365)
    can_manage = _has_permission(
        db, current_user, "PLANNING_AVAILABILITY_MANAGE"
    )
    can_approve = _has_permission(
        db, current_user, "PLANNING_ABSENCE_APPROVE"
    )
    if can_manage or can_approve:
        users = (
            db.query(models.User)
            .filter(models.User.is_active == True)  # noqa: E712
            .order_by(models.User.first_name, models.User.last_name, models.User.username)
            .all()
        )
    else:
        user = _current_user_record(db, current_user)
        users = [user] if user and user.is_active else []
    visible_user_ids = [user.id for user in users]
    absences = (
        db.query(models.UserAbsence)
        .filter(
            models.UserAbsence.user_id.in_(visible_user_ids or [-1]),
            models.UserAbsence.start_at < end_at,
            models.UserAbsence.end_at > start_at,
        )
        .order_by(models.UserAbsence.start_at)
        .all()
    )
    absences_by_user: dict[int, list[dict]] = {user.id: [] for user in users}
    for absence in absences:
        absences_by_user.setdefault(absence.user_id, []).append(
            _serialize_absence(absence)
        )
    return {
        "users": [
            {
                "id": user.id,
                "name": _display_user(user),
                "username": user.username,
                "role": user.role,
                "weekly_hours": user.weekly_hours or 35.0,
                "work_schedule": _user_work_schedule(user),
                "absences": absences_by_user.get(user.id, []),
            }
            for user in users
        ],
        "can_edit": can_manage,
        "can_approve": can_approve,
        "timezone": "Europe/Paris",
    }


@router.put("/availability/{user_id}")
def update_user_availability(
    user_id: int,
    payload: WorkScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permissions("PLANNING_AVAILABILITY_MANAGE")
    ),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    schedule = _validated_work_schedule(payload.work_schedule)
    user.work_schedule = schedule
    user.weekly_hours = _schedule_weekly_hours(schedule)
    db.commit()
    db.refresh(user)
    return {
        "id": user.id,
        "weekly_hours": user.weekly_hours,
        "work_schedule": schedule,
    }


@router.post(
    "/availability/{user_id}/absences",
    status_code=status.HTTP_201_CREATED,
)
def create_user_absence(
    user_id: int,
    payload: UserAbsenceCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_VIEW")),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    requester = _current_user_record(db, current_user)
    can_approve = _has_permission(
        db, current_user, "PLANNING_ABSENCE_APPROVE"
    )
    if not requester or (requester.id != user_id and not can_approve):
        raise HTTPException(
            status_code=403,
            detail="Vous ne pouvez demander une absence que pour vous-même.",
        )
    overlapping = (
        db.query(models.UserAbsence)
        .filter(
            models.UserAbsence.user_id == user_id,
            models.UserAbsence.status.in_(["PENDING", "APPROVED"]),
            models.UserAbsence.start_at < payload.end_at,
            models.UserAbsence.end_at > payload.start_at,
        )
        .first()
    )
    if overlapping:
        raise HTTPException(
            status_code=409,
            detail="Une indisponibilité existe déjà sur cette période.",
        )
    absence = models.UserAbsence(
        user_id=user_id,
        start_at=payload.start_at,
        end_at=payload.end_at,
        absence_type=payload.absence_type,
        status="PENDING",
        reason=payload.reason,
        created_by=current_user.get("sub") or "planning",
    )
    db.add(absence)
    db.commit()
    db.refresh(absence)
    return _serialize_absence(absence)


@router.patch("/availability/absences/{absence_id}/review")
def review_user_absence(
    absence_id: int,
    payload: schemas.UserAbsenceReview,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permissions("PLANNING_ABSENCE_APPROVE")
    ),
):
    absence = db.get(models.UserAbsence, absence_id)
    if not absence:
        raise HTTPException(status_code=404, detail="Demande d'absence introuvable")
    if absence.status != "PENDING":
        raise HTTPException(status_code=409, detail="Cette demande a déjà été traitée")
    if payload.status == "APPROVED":
        overlapping = (
            db.query(models.UserAbsence)
            .filter(
                models.UserAbsence.id != absence.id,
                models.UserAbsence.user_id == absence.user_id,
                models.UserAbsence.status == "APPROVED",
                models.UserAbsence.start_at < absence.end_at,
                models.UserAbsence.end_at > absence.start_at,
            )
            .first()
        )
        if overlapping:
            raise HTTPException(
                status_code=409,
                detail="Une absence validée existe déjà sur cette période.",
            )
    reviewer = _current_user_record(db, current_user)
    absence.status = payload.status
    absence.reviewed_by_user_id = reviewer.id if reviewer else None
    absence.reviewed_at = utcnow()
    absence.review_note = (payload.review_note or "").strip() or None
    db.commit()
    db.refresh(absence)
    return _serialize_absence(absence)


@router.delete("/availability/absences/{absence_id}")
def delete_user_absence(
    absence_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_VIEW")),
):
    absence = (
        db.query(models.UserAbsence)
        .filter(models.UserAbsence.id == absence_id)
        .first()
    )
    if not absence:
        raise HTTPException(status_code=404, detail="Indisponibilité introuvable")
    requester = _current_user_record(db, current_user)
    can_approve = _has_permission(
        db, current_user, "PLANNING_ABSENCE_APPROVE"
    )
    if not requester or (requester.id != absence.user_id and not can_approve):
        raise HTTPException(status_code=403, detail="Suppression non autorisée")
    if absence.status == "APPROVED" and not can_approve:
        raise HTTPException(
            status_code=409,
            detail="Une absence validée doit être annulée par un responsable.",
        )
    db.delete(absence)
    db.commit()
    return {"status": "deleted"}


@router.get("/execution-reasons")
def list_planning_execution_reasons(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_VIEW")),
):
    if include_inactive and not _has_permission(
        db,
        current_user,
        "PLANNING_RESOURCE_MANAGE",
    ):
        raise HTTPException(
            status_code=403,
            detail="Les motifs inactifs sont réservés aux responsables planning.",
        )
    query = db.query(models.PlanningExecutionReason)
    if not include_inactive:
        query = query.filter(
            models.PlanningExecutionReason.is_active == True  # noqa: E712
        )
    reasons = query.order_by(
        models.PlanningExecutionReason.action,
        models.PlanningExecutionReason.sort_order,
        models.PlanningExecutionReason.label,
    ).all()
    return [_serialize_execution_reason(reason) for reason in reasons]


@router.post("/execution-reasons", status_code=status.HTTP_201_CREATED)
def create_planning_execution_reason(
    payload: PlanningExecutionReasonCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permissions("PLANNING_RESOURCE_MANAGE")
    ),
):
    existing = (
        db.query(models.PlanningExecutionReason)
        .filter(
            models.PlanningExecutionReason.action == payload.action,
            models.PlanningExecutionReason.code == payload.code,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Ce code de motif existe déjà pour cette action.",
        )
    _, actor_name = _actor_identity(db, current_user)
    reason = models.PlanningExecutionReason(
        action=payload.action,
        code=payload.code,
        label=payload.label,
        description=payload.description,
        requires_comment=payload.requires_comment,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
        created_by=actor_name,
    )
    db.add(reason)
    db.commit()
    db.refresh(reason)
    return _serialize_execution_reason(reason)


@router.patch("/execution-reasons/{reason_id}")
def update_planning_execution_reason(
    reason_id: int,
    payload: PlanningExecutionReasonUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permissions("PLANNING_RESOURCE_MANAGE")
    ),
):
    reason = db.get(models.PlanningExecutionReason, reason_id)
    if not reason:
        raise HTTPException(status_code=404, detail="Motif introuvable")
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(reason, field, value)
    db.commit()
    db.refresh(reason)
    return _serialize_execution_reason(reason)


@router.get("/alert-rules")
def list_planning_alert_rules(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_VIEW")),
):
    rules = (
        db.query(models.PlanningAlertRule)
        .order_by(models.PlanningAlertRule.id)
        .all()
    )
    return [serialize_alert_rule(rule) for rule in rules]


@router.patch("/alert-rules/{rule_id}")
def update_planning_alert_rule(
    rule_id: int,
    payload: PlanningAlertRuleUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permissions("PLANNING_RESOURCE_MANAGE")
    ),
):
    rule = db.get(models.PlanningAlertRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Règle d’alerte introuvable")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return serialize_alert_rule(rule)


@router.post("/alerts/evaluate")
def evaluate_planning_alerts(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_EDIT")),
):
    created = evaluate_operational_alerts(db)
    db.commit()
    return {"created": created}


def _incident_query(db: Session):
    return db.query(models.PlanningIncident).options(
        selectinload(models.PlanningIncident.responsible_user),
        selectinload(models.PlanningIncident.assigned_manager),
        selectinload(models.PlanningIncident.history),
    )


def _incident_payload(
    db: Session,
    incident: models.PlanningIncident,
    *,
    include_history: bool = False,
) -> dict:
    payload = serialize_incident(incident, include_history=include_history)
    rule = (
        db.query(models.PlanningAlertRule.notify_pwa)
        .filter(models.PlanningAlertRule.code == incident.alert_code)
        .first()
    )
    payload["notify_pwa"] = bool(rule[0]) if rule else True
    return payload


def _incident_for_user(
    db: Session,
    incident_id: int,
    current_user: dict,
) -> models.PlanningIncident:
    incident = _incident_query(db).filter(
        models.PlanningIncident.id == incident_id
    ).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident introuvable")
    if _has_edit_permission(db, current_user):
        return incident
    user = _current_user_record(db, current_user)
    if not user or user.id != incident.responsible_user_id:
        raise HTTPException(status_code=403, detail="Incident non accessible")
    return incident


@router.get("/incidents")
def list_planning_incidents(
    incident_status: Optional[str] = None,
    severity: Optional[str] = None,
    responsible_user_id: Optional[int] = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_VIEW")),
):
    evaluate_operational_alerts(db)
    db.commit()
    query = _incident_query(db)
    summary_query = db.query(models.PlanningIncident)
    if not _has_edit_permission(db, current_user):
        user = _current_user_record(db, current_user)
        if not user:
            raise HTTPException(status_code=403, detail="Utilisateur introuvable")
        query = query.filter(
            models.PlanningIncident.responsible_user_id == user.id
        )
        summary_query = summary_query.filter(
            models.PlanningIncident.responsible_user_id == user.id
        )
    if incident_status:
        statuses = {
            value.strip().upper()
            for value in incident_status.split(",")
            if value.strip()
        }
        query = query.filter(models.PlanningIncident.status.in_(statuses))
    if severity:
        severities = {
            value.strip().upper()
            for value in severity.split(",")
            if value.strip()
        }
        query = query.filter(models.PlanningIncident.severity.in_(severities))
    if responsible_user_id:
        query = query.filter(
            models.PlanningIncident.responsible_user_id == responsible_user_id
        )
    incidents = query.order_by(
        models.PlanningIncident.status,
        models.PlanningIncident.triggered_at.desc(),
    ).limit(min(max(limit, 1), 500)).all()
    summary_incidents = summary_query.all()
    summary = {
        "open": sum(item.status == "OPEN" for item in summary_incidents),
        "acknowledged": sum(
            item.status == "ACKNOWLEDGED" for item in summary_incidents
        ),
        "resolved": sum(item.status == "RESOLVED" for item in summary_incidents),
        "critical": sum(
            item.status != "RESOLVED" and item.severity == "CRITICAL"
            for item in summary_incidents
        ),
        "escalated": sum(
            item.status != "RESOLVED" and item.escalation_level > 0
            for item in summary_incidents
        ),
    }
    return {
        "summary": summary,
        "incidents": [_incident_payload(db, item) for item in incidents],
    }


@router.get("/incidents/{incident_id}")
def get_planning_incident(
    incident_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_VIEW")),
):
    incident = _incident_for_user(db, incident_id, current_user)
    return _incident_payload(db, incident, include_history=True)


@router.post("/incidents/{incident_id}/acknowledge")
def acknowledge_planning_incident(
    incident_id: int,
    payload: PlanningIncidentAcknowledge,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_EDIT")),
):
    incident = _incident_for_user(db, incident_id, current_user)
    if incident.status == "RESOLVED":
        raise HTTPException(status_code=409, detail="Cet incident est déjà résolu")
    actor_id, actor_name = _actor_identity(db, current_user)
    manager_id = payload.assigned_manager_user_id or actor_id
    _active_user(db, manager_id)
    previous_status = incident.status
    incident.status = "ACKNOWLEDGED"
    incident.acknowledged_at = utcnow()
    incident.acknowledged_by_user_id = actor_id
    incident.assigned_manager_user_id = manager_id
    incident.next_escalation_at = None
    add_incident_history(
        db,
        incident,
        "ACKNOWLEDGED",
        actor_user_id=actor_id,
        actor_name=actor_name,
        previous_status=previous_status,
        comment=payload.comment,
        changes={"assigned_manager_user_id": manager_id},
    )
    db.commit()
    return _incident_payload(
        db,
        _incident_query(db).filter(
            models.PlanningIncident.id == incident.id
        ).one(),
        include_history=True,
    )


@router.post("/incidents/{incident_id}/reassign")
def reassign_planning_incident(
    incident_id: int,
    payload: PlanningIncidentReassign,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_EDIT")),
):
    incident = _incident_for_user(db, incident_id, current_user)
    if incident.status == "RESOLVED":
        raise HTTPException(status_code=409, detail="Cet incident est déjà résolu")
    actor_id, actor_name = _actor_identity(db, current_user)
    changes = {}
    if payload.assigned_manager_user_id is not None:
        target_manager = _active_user(db, payload.assigned_manager_user_id)
        changes["assigned_manager_user_id"] = {
            "from": incident.assigned_manager_user_id,
            "to": payload.assigned_manager_user_id,
        }
        incident.assigned_manager_user_id = payload.assigned_manager_user_id
        db.add(
            models.PlanningNotification(
                user_id=target_manager.id,
                task_id=incident.task_id,
                source_type=incident.source_type,
                source_id=incident.source_id,
                incident_id=incident.id,
                notification_type="INCIDENT_REASSIGNED",
                title="Pilotage d’incident affecté",
                message=f"{incident.title} · par {actor_name}",
                deduplication_key=(
                    f"INCIDENT_MANAGER:{incident.id}:{target_manager.id}:"
                    f"{utcnow().strftime('%Y%m%d%H%M%S%f')}"
                ),
            )
        )
    if payload.responsible_user_id is not None:
        target_user = _active_user(db, payload.responsible_user_id)
        changes["responsible_user_id"] = {
            "from": incident.responsible_user_id,
            "to": payload.responsible_user_id,
        }
        incident.responsible_user_id = payload.responsible_user_id
        state = db.get(
            models.ScheduleExecutionState,
            incident.execution_state_id,
        )
        if state:
            state.assigned_user_id = payload.responsible_user_id
        source_record, _, source_title, _ = _execution_source(
            db,
            incident.source_type,
            incident.source_id,
        )
        if source_record:
            _assign_execution_source(
                incident.source_type,
                source_record,
                target_user,
            )
        if incident.task_id:
            task = db.get(models.CalendarTask, incident.task_id)
            if task:
                task.assigned_user_id = payload.responsible_user_id
        db.add(
            models.PlanningNotification(
                user_id=target_user.id,
                task_id=incident.task_id,
                source_type=incident.source_type,
                source_id=incident.source_id,
                incident_id=incident.id,
                notification_type="INCIDENT_REASSIGNED",
                title="Incident planning réaffecté",
                message=f"{source_title} · par {actor_name}",
                deduplication_key=(
                    f"INCIDENT_REASSIGNED:{incident.id}:{target_user.id}:"
                    f"{utcnow().strftime('%Y%m%d%H%M%S%f')}"
                ),
            )
        )
    add_incident_history(
        db,
        incident,
        "REASSIGNED",
        actor_user_id=actor_id,
        actor_name=actor_name,
        previous_status=incident.status,
        comment=payload.comment,
        changes=changes,
    )
    db.commit()
    return _incident_payload(
        db,
        _incident_query(db).filter(
            models.PlanningIncident.id == incident.id
        ).one(),
        include_history=True,
    )


@router.post("/incidents/{incident_id}/comments")
def comment_planning_incident(
    incident_id: int,
    payload: PlanningIncidentComment,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_VIEW")),
):
    incident = _incident_for_user(db, incident_id, current_user)
    actor_id, actor_name = _actor_identity(db, current_user)
    add_incident_history(
        db,
        incident,
        "COMMENTED",
        actor_user_id=actor_id,
        actor_name=actor_name,
        previous_status=incident.status,
        comment=payload.comment,
    )
    db.commit()
    return _incident_payload(
        db,
        _incident_query(db).filter(
            models.PlanningIncident.id == incident.id
        ).one(),
        include_history=True,
    )


@router.post("/incidents/{incident_id}/resolve")
def resolve_planning_incident(
    incident_id: int,
    payload: PlanningIncidentResolve,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_EDIT")),
):
    incident = _incident_for_user(db, incident_id, current_user)
    if incident.status == "RESOLVED":
        raise HTTPException(status_code=409, detail="Cet incident est déjà résolu")
    actor_id, actor_name = _actor_identity(db, current_user)
    previous_status = incident.status
    incident.status = "RESOLVED"
    incident.resolved_at = utcnow()
    incident.resolved_by_user_id = actor_id
    incident.resolution_note = payload.comment
    incident.next_escalation_at = None
    add_incident_history(
        db,
        incident,
        "RESOLVED",
        actor_user_id=actor_id,
        actor_name=actor_name,
        previous_status=previous_status,
        comment=payload.comment,
    )
    db.commit()
    return _incident_payload(
        db,
        _incident_query(db).filter(
            models.PlanningIncident.id == incident.id
        ).one(),
        include_history=True,
    )


@router.get("/skills")
def list_planning_skills(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_VIEW")),
):
    skills = (
        db.query(models.PlanningSkill)
        .filter(models.PlanningSkill.is_active == True)  # noqa: E712
        .order_by(models.PlanningSkill.category, models.PlanningSkill.name)
        .all()
    )
    return [_serialize_skill(skill) for skill in skills]


@router.post("/skills", status_code=status.HTTP_201_CREATED)
def create_planning_skill(
    payload: schemas.PlanningSkillCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permissions("PLANNING_RESOURCE_MANAGE")
    ),
):
    code = payload.code.strip().upper().replace(" ", "_")
    if db.query(models.PlanningSkill).filter(models.PlanningSkill.code == code).first():
        raise HTTPException(status_code=409, detail="Ce code de compétence existe déjà")
    skill = models.PlanningSkill(
        code=code,
        name=payload.name.strip(),
        category=payload.category.strip().upper(),
        description=(payload.description or "").strip() or None,
        requires_expiry=payload.requires_expiry,
        is_active=payload.is_active,
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return _serialize_skill(skill)


@router.get("/users/{user_id}/skills")
def get_user_planning_skills(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_VIEW")),
):
    requester = _current_user_record(db, current_user)
    if (
        not _has_edit_permission(db, current_user)
        and (not requester or requester.id != user_id)
    ):
        raise HTTPException(status_code=403, detail="Compétences non accessibles")
    rows = (
        db.query(models.UserPlanningSkill)
        .options(selectinload(models.UserPlanningSkill.skill))
        .filter(models.UserPlanningSkill.user_id == user_id)
        .all()
    )
    return [
        {
            "id": row.id,
            "user_id": row.user_id,
            "skill_id": row.skill_id,
            "level": row.level,
            "is_certified": row.is_certified,
            "certificate_reference": row.certificate_reference,
            "acquired_at": row.acquired_at,
            "valid_until": row.valid_until,
            "notes": row.notes,
            "skill": _serialize_skill(row.skill),
        }
        for row in rows
    ]


@router.put("/users/{user_id}/skills")
def replace_user_planning_skills(
    user_id: int,
    payload: UserSkillsUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permissions("PLANNING_RESOURCE_MANAGE")
    ),
):
    if not db.get(models.User, user_id):
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    skill_ids = [item.skill_id for item in payload.skills]
    if len(skill_ids) != len(set(skill_ids)):
        raise HTTPException(status_code=422, detail="Compétence en double")
    known_skills = {
        item.id: item
        for item in db.query(models.PlanningSkill)
        .filter(models.PlanningSkill.id.in_(skill_ids or [-1]))
        .all()
    }
    if set(known_skills) != set(skill_ids):
        raise HTTPException(status_code=422, detail="Compétence introuvable")
    missing_expiry = [
        known_skills[item.skill_id].name
        for item in payload.skills
        if known_skills[item.skill_id].requires_expiry
        and item.valid_until is None
    ]
    if missing_expiry:
        raise HTTPException(
            status_code=422,
            detail=(
                "Date de validité obligatoire pour : "
                + ", ".join(sorted(missing_expiry))
            ),
        )
    db.query(models.UserPlanningSkill).filter(
        models.UserPlanningSkill.user_id == user_id
    ).delete(synchronize_session=False)
    for item in payload.skills:
        db.add(
            models.UserPlanningSkill(
                user_id=user_id,
                skill_id=item.skill_id,
                level=item.level,
                is_certified=item.is_certified,
                certificate_reference=item.certificate_reference,
                acquired_at=item.acquired_at,
                valid_until=item.valid_until,
                notes=item.notes,
            )
        )
    db.commit()
    return get_user_planning_skills(user_id, db, current_user)


@router.get("/resources")
def list_planning_resources(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_VIEW")),
):
    resources = (
        db.query(models.PlanningResource)
        .options(selectinload(models.PlanningResource.members))
        .order_by(models.PlanningResource.resource_type, models.PlanningResource.name)
        .all()
    )
    return [_serialize_resource(resource) for resource in resources]


@router.post("/resources", status_code=status.HTTP_201_CREATED)
def create_planning_resource(
    payload: schemas.PlanningResourceCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permissions("PLANNING_RESOURCE_MANAGE")
    ),
):
    code = payload.code.strip().upper().replace(" ", "_")
    if db.query(models.PlanningResource).filter(models.PlanningResource.code == code).first():
        raise HTTPException(status_code=409, detail="Ce code ressource existe déjà")
    if payload.station_id and not db.get(models.Station, payload.station_id):
        raise HTTPException(status_code=422, detail="Station introuvable")
    resource = models.PlanningResource(
        code=code,
        name=payload.name.strip(),
        resource_type=payload.resource_type.strip().upper(),
        status=payload.status.strip().upper(),
        station_id=payload.station_id,
        capacity=payload.capacity,
        timezone=payload.timezone,
        details=payload.details,
        is_active=payload.is_active,
    )
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return _serialize_resource(resource)


@router.put("/resources/{resource_id}/members")
def replace_planning_resource_members(
    resource_id: int,
    payload: ResourceMembersUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permissions("PLANNING_RESOURCE_MANAGE")
    ),
):
    resource = db.get(models.PlanningResource, resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Ressource introuvable")
    user_ids = [item.user_id for item in payload.members]
    if len(user_ids) != len(set(user_ids)):
        raise HTTPException(status_code=422, detail="Collaborateur en double")
    known_users = {
        user.id
        for user in db.query(models.User)
        .filter(
            models.User.id.in_(user_ids or [-1]),
            models.User.is_active == True,  # noqa: E712
        )
        .all()
    }
    if known_users != set(user_ids):
        raise HTTPException(status_code=422, detail="Collaborateur introuvable")
    db.query(models.PlanningResourceMember).filter(
        models.PlanningResourceMember.resource_id == resource_id
    ).delete(synchronize_session=False)
    for item in payload.members:
        db.add(
            models.PlanningResourceMember(
                resource_id=resource_id,
                user_id=item.user_id,
                member_role=(item.member_role or "").strip() or None,
                is_lead=item.is_lead,
            )
        )
    db.commit()
    refreshed = (
        db.query(models.PlanningResource)
        .options(selectinload(models.PlanningResource.members))
        .filter(models.PlanningResource.id == resource_id)
        .one()
    )
    return _serialize_resource(refreshed)


@router.get("/resources/{resource_id}/unavailabilities")
def list_planning_resource_unavailabilities(
    resource_id: int,
    start_at: Optional[datetime] = None,
    end_at: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_VIEW")),
):
    if not db.get(models.PlanningResource, resource_id):
        raise HTTPException(status_code=404, detail="Ressource introuvable")
    query = db.query(models.PlanningResourceUnavailability).filter(
        models.PlanningResourceUnavailability.resource_id == resource_id
    )
    if start_at:
        query = query.filter(
            models.PlanningResourceUnavailability.end_at > _naive_utc(start_at)
        )
    if end_at:
        query = query.filter(
            models.PlanningResourceUnavailability.start_at < _naive_utc(end_at)
        )
    return query.order_by(models.PlanningResourceUnavailability.start_at).all()


@router.post(
    "/resources/{resource_id}/unavailabilities",
    status_code=status.HTTP_201_CREATED,
)
def create_planning_resource_unavailability(
    resource_id: int,
    payload: schemas.PlanningResourceUnavailabilityCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permissions("PLANNING_RESOURCE_MANAGE")
    ),
):
    if payload.resource_id != resource_id:
        raise HTTPException(status_code=422, detail="Ressource incohérente")
    if not db.get(models.PlanningResource, resource_id):
        raise HTTPException(status_code=404, detail="Ressource introuvable")
    start_at = _naive_utc(payload.start_at)
    end_at = _naive_utc(payload.end_at)
    if end_at <= start_at:
        raise HTTPException(status_code=422, detail="Période indisponible invalide")
    unavailability = models.PlanningResourceUnavailability(
        resource_id=resource_id,
        start_at=start_at,
        end_at=end_at,
        reason=payload.reason.strip(),
        unavailability_type=payload.unavailability_type.strip().upper(),
        created_by=current_user.get("sub") or "planning",
    )
    db.add(unavailability)
    db.commit()
    db.refresh(unavailability)
    return unavailability


@router.delete("/resources/unavailabilities/{unavailability_id}")
def delete_planning_resource_unavailability(
    unavailability_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permissions("PLANNING_RESOURCE_MANAGE")
    ),
):
    unavailability = db.get(
        models.PlanningResourceUnavailability, unavailability_id
    )
    if not unavailability:
        raise HTTPException(status_code=404, detail="Indisponibilité introuvable")
    db.delete(unavailability)
    db.commit()
    return {"status": "deleted"}


@router.get("/closures")
def list_planning_closures(
    start_at: Optional[datetime] = None,
    end_at: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_VIEW")),
):
    query = db.query(models.PlanningClosure)
    if start_at:
        query = query.filter(models.PlanningClosure.end_at > _naive_utc(start_at))
    if end_at:
        query = query.filter(models.PlanningClosure.start_at < _naive_utc(end_at))
    return query.order_by(models.PlanningClosure.start_at).all()


@router.post("/closures", status_code=status.HTTP_201_CREATED)
def create_planning_closure(
    payload: schemas.PlanningClosureCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permissions("PLANNING_AVAILABILITY_MANAGE")
    ),
):
    if payload.end_at <= payload.start_at:
        raise HTTPException(status_code=422, detail="Période de fermeture invalide")
    closure = models.PlanningClosure(
        **payload.model_dump(),
        created_by=current_user.get("sub") or "planning",
    )
    db.add(closure)
    db.commit()
    db.refresh(closure)
    return closure


@router.delete("/closures/{closure_id}")
def delete_planning_closure(
    closure_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permissions("PLANNING_AVAILABILITY_MANAGE")
    ),
):
    closure = db.get(models.PlanningClosure, closure_id)
    if not closure:
        raise HTTPException(status_code=404, detail="Fermeture introuvable")
    db.delete(closure)
    db.commit()
    return {"status": "deleted"}


def _team_insights(
    events: list[dict],
    unscheduled: list[dict],
    users: list[models.User],
    absences: list[models.UserAbsence],
    start_at: datetime,
    end_at: datetime,
    *,
    owner_id: Optional[int] = None,
):
    now = utcnow()
    users_by_id = {
        user.id: user
        for user in users
        if owner_id is None or user.id == owner_id
    }
    events_by_user: dict[int, list[dict]] = {
        user_id: [] for user_id in users_by_id
    }
    for event in events:
        event_owner_id = event.get("owner_id")
        if event_owner_id is not None:
            events_by_user.setdefault(event_owner_id, []).append(event)
    absences_by_user: dict[int, list[models.UserAbsence]] = {
        user_id: [] for user_id in users_by_id
    }
    for absence in absences:
        if absence.user_id in absences_by_user:
            absences_by_user[absence.user_id].append(absence)

    conflict_pairs = []
    conflict_count_by_user: dict[int, int] = {}
    for user_id, user_events in events_by_user.items():
        ordered = sorted(
            (event for event in user_events if event.get("start_at")),
            key=lambda event: event["start_at"],
        )
        for index, first in enumerate(ordered):
            first_end = _event_end(first)
            if not first_end:
                continue
            for second in ordered[index + 1:]:
                if second["start_at"] >= first_end:
                    break
                if _events_overlap(first, second):
                    conflict_pairs.append((user_id, first, second))
                    conflict_count_by_user[user_id] = (
                        conflict_count_by_user.get(user_id, 0) + 1
                    )

    team_load = []
    for user_id, user_events in events_by_user.items():
        user = users_by_id.get(user_id)
        owner_name = _display_user(user)
        if not owner_name and user_events:
            owner_name = user_events[0].get("owner_name")
        planned_hours = round(
            sum(
                _planned_hours(event, start_at, end_at)
                for event in user_events
                if event.get("source_type") != "USER_ABSENCE"
            ),
            2,
        )
        capacity_per_user, absence_hours = _working_capacity_hours(
            user,
            start_at,
            end_at,
            absences_by_user.get(user_id, []),
        )
        utilization_pct = (
            round(planned_hours / capacity_per_user * 100, 1)
            if capacity_per_user
            else (100.0 if planned_hours else 0.0)
        )
        if utilization_pct > 100:
            load_status = "OVERLOADED"
        elif utilization_pct >= 80:
            load_status = "BUSY"
        else:
            load_status = "NORMAL"
        team_load.append(
            {
                "user_id": user_id,
                "owner_id": user_id,
                "name": owner_name or f"Utilisateur {user_id}",
                "event_count": len(user_events),
                "planned_hours": planned_hours,
                "capacity_hours": capacity_per_user,
                "contract_hours": user.weekly_hours or 35.0,
                "absence_hours": absence_hours,
                "absence_count": len(absences_by_user.get(user_id, [])),
                "utilization_pct": utilization_pct,
                "overdue_count": sum(
                    1 for event in user_events if _is_overdue(event, now)
                ),
                "conflict_count": conflict_count_by_user.get(user_id, 0),
                "conflicts": conflict_count_by_user.get(user_id, 0),
                "status": load_status,
                "overloaded": load_status == "OVERLOADED",
            }
        )
    team_load.sort(
        key=lambda load: (
            load["status"] != "OVERLOADED",
            load["status"] != "BUSY",
            -load["utilization_pct"],
            load["name"],
        )
    )

    alerts = []
    for load in team_load:
        if load["status"] == "OVERLOADED":
            alerts.append(
                {
                    "id": f"OVERLOAD:{load['user_id']}",
                    "type": "OVERLOAD",
                    "severity": "CRITICAL",
                    "message": (
                        f"{load['name']} est planifié à "
                        f"{load['utilization_pct']:.1f}% de sa capacité."
                    ),
                    "user_id": load["user_id"],
                    "user_name": load["name"],
                    "event_ids": [],
                }
            )

    for user_id, first, second in conflict_pairs:
        user = users_by_id.get(user_id)
        user_name = _display_user(user) or first.get("owner_name")
        alerts.append(
            {
                "id": f"CONFLICT:{first['id']}:{second['id']}",
                "type": "CONFLICT",
                "severity": "CRITICAL",
                "message": (
                    f"{user_name or 'Ce collaborateur'} a deux actions "
                    "qui se chevauchent."
                ),
                "user_id": user_id,
                "user_name": user_name,
                "event_ids": [first["id"], second["id"]],
                "start_at": max(first["start_at"], second["start_at"]),
                "end_at": min(_event_end(first), _event_end(second)),
            }
        )

    for event in events:
        if _is_overdue(event, now):
            alerts.append(
                {
                    "id": f"OVERDUE:{event['id']}",
                    "type": "OVERDUE",
                    "severity": "WARNING",
                    "message": f"Action en retard : {event['title']}.",
                    "user_id": event.get("owner_id"),
                    "user_name": event.get("owner_name"),
                    "event_ids": [event["id"]],
                    "source_type": event["source_type"],
                    "source_id": event["source_id"],
                    "start_at": event.get("start_at"),
                    "end_at": _event_end(event),
                }
            )

    seen_unassigned = set()
    for event in [*events, *unscheduled]:
        if (
            event["source_type"] not in EDITABLE_SOURCES
            or event.get("owner_id") is not None
            or event.get("owner_name")
            or _is_completed(event.get("status"))
            or event["id"] in seen_unassigned
        ):
            continue
        seen_unassigned.add(event["id"])
        alerts.append(
            {
                "id": f"UNASSIGNED:{event['id']}",
                "type": "UNASSIGNED",
                "severity": "WARNING",
                "message": f"Action sans responsable : {event['title']}.",
                "user_id": None,
                "user_name": None,
                "event_ids": [event["id"]],
                "source_type": event["source_type"],
                "source_id": event["source_id"],
                "start_at": event.get("start_at"),
                "end_at": _event_end(event),
            }
        )

    return team_load, alerts, len(conflict_pairs)


@router.get("/meta")
def get_schedule_meta(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_VIEW")),
):
    can_edit = _has_edit_permission(db, current_user)
    if can_edit:
        users = (
            db.query(models.User)
            .filter(models.User.is_active == True)  # noqa: E712
            .order_by(
                models.User.first_name,
                models.User.last_name,
                models.User.username,
            )
            .all()
        )
        clients = (
            db.query(models.Client)
            .options(selectinload(models.Client.site_addresses))
            .filter(models.Client.is_active == True)  # noqa: E712
            .order_by(models.Client.name)
            .limit(500)
            .all()
        )
        signed_orders = (
            db.query(models.SaleOrder)
            .filter(
                or_(
                    models.SaleOrder.signed_at.is_not(None),
                    models.SaleOrder.status.in_(["VALIDATED", "DELIVERED"]),
                )
            )
            .order_by(models.SaleOrder.created_at.desc())
            .limit(300)
            .all()
        )
    else:
        user = _current_user_record(db, current_user)
        users = [user] if user and user.is_active else []
        clients = []
        signed_orders = []
    skills = (
        db.query(models.PlanningSkill)
        .filter(models.PlanningSkill.is_active == True)  # noqa: E712
        .order_by(models.PlanningSkill.category, models.PlanningSkill.name)
        .all()
    )
    resources = (
        db.query(models.PlanningResource)
        .options(selectinload(models.PlanningResource.members))
        .filter(models.PlanningResource.is_active == True)  # noqa: E712
        .order_by(models.PlanningResource.resource_type, models.PlanningResource.name)
        .all()
    )
    stations = (
        db.query(models.Station)
        .order_by(models.Station.order_index, models.Station.display_name)
        .all()
        if can_edit
        else []
    )
    return {
        "users": [
            {
                "id": user.id,
                "name": _display_user(user),
                "username": user.username,
                "role": user.role,
                "weekly_hours": user.weekly_hours or 35.0,
                "work_schedule": _user_work_schedule(user),
            }
            for user in users
        ],
        "clients": [
            {
                "id": client.id,
                "name": client.name,
                "default_site": (
                    {
                        "id": site.id,
                        "label": site.label,
                        "address": site.formatted_address,
                        "latitude": site.latitude,
                        "longitude": site.longitude,
                    }
                    if (
                        site := next(
                            (
                                item
                                for item in client.site_addresses
                                if item.is_default
                            ),
                            client.site_addresses[0]
                            if client.site_addresses
                            else None,
                        )
                    )
                    else None
                ),
            }
            for client in clients
        ],
        "sale_orders": [
            {
                "id": order.id,
                "reference": order.reference,
                "client_name": order.client_name,
                "status": order.status,
            }
            for order in signed_orders
        ],
        "categories": sorted(TASK_CATEGORIES),
        "skills": [_serialize_skill(skill) for skill in skills],
        "resources": [_serialize_resource(resource) for resource in resources],
        "stations": [
            {
                "id": station.id,
                "name": station.display_name or station.code,
            }
            for station in stations
        ],
        "can_edit": can_edit,
        "can_manage_availability": _has_permission(
            db,
            current_user,
            "PLANNING_AVAILABILITY_MANAGE",
        ),
        "can_approve_absences": _has_permission(
            db,
            current_user,
            "PLANNING_ABSENCE_APPROVE",
        ),
        "can_manage_resources": _has_permission(
            db,
            current_user,
            "PLANNING_RESOURCE_MANAGE",
        ),
    }


def _candidate_working_intervals(
    user: models.User,
    start_at: datetime,
    end_at: datetime,
) -> list[dict]:
    intervals = []
    local_day = (
        start_at.replace(tzinfo=timezone.utc)
        .astimezone(PARIS_TIMEZONE)
        .date()
    )
    last_day = (
        (end_at - timedelta(microseconds=1))
        .replace(tzinfo=timezone.utc)
        .astimezone(PARIS_TIMEZONE)
        .date()
    )
    schedule = _user_work_schedule(user)
    while local_day <= last_day:
        for start_value, end_value in schedule.get(str(local_day.weekday()), []):
            interval_start, interval_end = _local_schedule_interval(
                local_day, start_value, end_value
            )
            intervals.append({"start": interval_start, "end": interval_end})
        local_day += timedelta(days=1)
    return intervals


@router.post("/suggestions")
def suggest_schedule_assignments(
    payload: PlanningSuggestionRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_EDIT")),
):
    users = (
        db.query(models.User)
        .options(
            selectinload(models.User.planning_skills)
            .selectinload(models.UserPlanningSkill.skill),
            selectinload(models.User.stations),
        )
        .filter(models.User.is_active == True)  # noqa: E712
        .all()
    )
    required_skills = {
        skill.id: skill.code
        for skill in db.query(models.PlanningSkill)
        .filter(models.PlanningSkill.id.in_(payload.required_skill_ids or [-1]))
        .all()
    }
    if set(required_skills) != set(payload.required_skill_ids):
        raise HTTPException(status_code=422, detail="Compétence requise introuvable")

    resources = (
        db.query(models.PlanningResource)
        .options(selectinload(models.PlanningResource.unavailabilities))
        .filter(models.PlanningResource.id.in_(payload.required_resource_ids or [-1]))
        .all()
    )
    if {resource.id for resource in resources} != set(payload.required_resource_ids):
        raise HTTPException(status_code=422, detail="Ressource requise introuvable")

    absences = (
        db.query(models.UserAbsence)
        .filter(
            models.UserAbsence.status == "APPROVED",
            models.UserAbsence.start_at < payload.window_end,
            models.UserAbsence.end_at > payload.window_start,
        )
        .all()
    )
    closures = (
        db.query(models.PlanningClosure)
        .filter(
            models.PlanningClosure.affects_capacity == True,  # noqa: E712
            models.PlanningClosure.start_at < payload.window_end,
            models.PlanningClosure.end_at > payload.window_start,
        )
        .all()
    )
    tasks = (
        db.query(models.CalendarTask)
        .options(selectinload(models.CalendarTask.resource_assignments))
        .filter(
            models.CalendarTask.status != "CANCELLED",
            _overlaps(
                models.CalendarTask.start_at,
                models.CalendarTask.end_at,
                payload.window_start,
                payload.window_end,
            ),
        )
        .all()
    )

    candidates = []
    for user in users:
        valid_skills = [
            row.skill.code
            for row in user.planning_skills
            if row.skill
            and row.skill.is_active
            and (
                row.valid_until is None
                or row.valid_until >= payload.window_start
            )
        ]
        candidates.append(
            {
                "id": user.id,
                "skills": valid_skills,
                "capacity_hours": user.weekly_hours or 35.0,
                "profession": user.job_title or user.role or "NON RENSEIGNÉ",
                "station_ids": [station.id for station in user.stations],
                "working_intervals": _candidate_working_intervals(
                    user, payload.window_start, payload.window_end
                ),
            }
        )
    engine_resources = [
        {
            "id": resource.id,
            "active": resource.is_active and resource.status == "ACTIVE",
            "unavailable_intervals": [
                {
                    "start": item.start_at,
                    "end": item.end_at,
                }
                for item in resource.unavailabilities
            ],
        }
        for resource in resources
    ]
    bookings = [
        {
            "id": task.id,
            "user_id": task.assigned_user_id,
            "resource_ids": [
                item.resource_id for item in task.resource_assignments
            ],
            "start": task.start_at,
            "end": _default_end(task.start_at, task.end_at),
            "location": {
                "id": task.location_label or task.location_address,
                "lat": task.latitude,
                "lon": task.longitude,
            },
        }
        for task in tasks
    ]
    engine_absences = [
        {
            "id": absence.id,
            "user_id": absence.user_id,
            "type": absence.absence_type,
            "start": absence.start_at,
            "end": absence.end_at,
        }
        for absence in absences
    ]
    engine_closures = [
        {
            "id": closure.id,
            "label": closure.name,
            "station_id": (
                closure.resource.station_id
                if closure.resource_id and closure.resource
                else None
            ),
            "start": closure.start_at,
            "end": closure.end_at,
        }
        for closure in closures
    ]
    task = {
        "duration_minutes": payload.duration_minutes,
        "required_skills": list(required_skills.values()),
        "required_resource_ids": payload.required_resource_ids,
        "location": {
            "id": payload.location_label,
            "lat": payload.latitude,
            "lon": payload.longitude,
        },
        "travel_margin_minutes": payload.travel_margin_minutes,
    }
    suggestions = suggest_assignments(
        task,
        candidates,
        payload.window_start,
        payload.window_end,
        step_minutes=payload.step_minutes,
        limit=payload.limit,
        bookings=bookings,
        resources=engine_resources,
        closures=engine_closures,
        absences=engine_absences,
    )
    users_by_id = {str(user.id): user for user in users}
    return [
        {
            **suggestion,
            "candidate_id": int(suggestion["candidate_id"]),
            "candidate_name": _display_user(
                users_by_id.get(str(suggestion["candidate_id"]))
            ),
        }
        for suggestion in suggestions
    ]


@router.get("/capacity")
def get_schedule_capacity(
    start_at: datetime,
    end_at: datetime,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_VIEW")),
):
    start_at = _naive_utc(start_at)
    end_at = _naive_utc(end_at)
    users = (
        db.query(models.User)
        .options(
            selectinload(models.User.planning_skills)
            .selectinload(models.UserPlanningSkill.skill),
            selectinload(models.User.stations),
        )
        .filter(models.User.is_active == True)  # noqa: E712
        .all()
    )
    approved_absences = (
        db.query(models.UserAbsence)
        .filter(
            models.UserAbsence.status == "APPROVED",
            models.UserAbsence.start_at < end_at,
            models.UserAbsence.end_at > start_at,
        )
        .all()
    )
    tasks = (
        db.query(models.CalendarTask)
        .options(selectinload(models.CalendarTask.resource_assignments))
        .filter(
            models.CalendarTask.status != "CANCELLED",
            _overlaps(
                models.CalendarTask.start_at,
                models.CalendarTask.end_at,
                start_at,
                end_at,
            ),
        )
        .all()
    )
    candidates = []
    for user in users:
        capacity, _ = _working_capacity_hours(
            user, start_at, end_at, approved_absences
        )
        trade_skills = sorted(
            row.skill.name
            for row in user.planning_skills
            if row.skill
            and row.skill.category == "TRADE"
            and (not row.valid_until or row.valid_until >= utcnow())
        )
        candidates.append(
            {
                "id": user.id,
                "profession": (
                    " / ".join(trade_skills)
                    or user.job_title
                    or user.role
                    or "NON RENSEIGNÉ"
                ),
                "capacity_hours": capacity,
                "station_ids": [station.id for station in user.stations],
            }
        )
    stations = [
        {
            "id": station.id,
            "name": station.display_name or station.code,
            "capacity_hours": round(
                sum(
                    candidate["capacity_hours"]
                    for candidate in candidates
                    if station.id in candidate["station_ids"]
                ),
                2,
            ),
        }
        for station in db.query(models.Station).all()
    ]
    assignments = [
        {
            "user_id": task.assigned_user_id,
            "station_id": next(
                (
                    assignment.resource.station_id
                    for assignment in task.resource_assignments
                    if assignment.resource
                    and assignment.resource.station_id
                ),
                None,
            ),
            "start": max(task.start_at, start_at),
            "end": min(_default_end(task.start_at, task.end_at), end_at),
        }
        for task in tasks
    ]
    return calculate_capacity(candidates, stations, assignments)


@router.get("/events")
def get_schedule_events(
    start_at: datetime,
    end_at: datetime,
    types: Optional[str] = None,
    owner_id: Optional[int] = None,
    include_unscheduled: bool = True,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_VIEW")),
):
    start_at = _naive_utc(start_at)
    end_at = _naive_utc(end_at)
    if end_at <= start_at:
        raise HTTPException(status_code=422, detail="Période invalide")
    if end_at - start_at > timedelta(days=124):
        raise HTTPException(status_code=422, detail="La période est limitée à 124 jours")
    if not _has_edit_permission(db, current_user):
        user = _current_user_record(db, current_user)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=403,
                detail="Profil planning personnel introuvable",
            )
        owner_id = user.id

    events = []
    unscheduled = []
    active_users = (
        db.query(models.User)
        .filter(models.User.is_active == True)  # noqa: E712
        .order_by(models.User.first_name, models.User.last_name, models.User.username)
        .all()
    )
    users_by_username = {
        user.username.casefold(): user for user in active_users if user.username
    }
    users_by_name = {
        name.casefold(): user
        for user in active_users
        if (name := _display_user(user))
    }

    tasks = (
        db.query(models.CalendarTask)
        .options(
            selectinload(models.CalendarTask.assigned_user),
            selectinload(models.CalendarTask.client),
            selectinload(models.CalendarTask.sale_order),
            selectinload(models.CalendarTask.skill_requirements)
            .selectinload(models.CalendarTaskSkillRequirement.skill),
            selectinload(models.CalendarTask.resource_assignments)
            .selectinload(models.CalendarTaskResourceAssignment.resource),
        )
        .filter(
            models.CalendarTask.status != "CANCELLED",
            _overlaps(
                models.CalendarTask.start_at,
                models.CalendarTask.end_at,
                start_at,
                end_at,
            ),
        )
        .all()
    )
    for task in tasks:
        events.append(
            _event(
                "CALENDAR_TASK",
                task.id,
                task.category,
                task.title,
                task.start_at,
                end_at=_default_end(task.start_at, task.end_at),
                status=task.status,
                owner_id=task.assigned_user_id,
                owner_name=_display_user(task.assigned_user),
                reference=task.sale_order.reference if task.sale_order else f"PLN-{task.id:05d}",
                client_name=task.client.name if task.client else (
                    task.sale_order.client_name if task.sale_order else None
                ),
                priority=task.priority,
                source_view="sales" if task.sale_order_id else None,
                source_url=(
                    f"/manager?view=sale-detail&id={task.sale_order_id}&from=sales"
                    if task.sale_order_id
                    else None
                ),
                subtitle=task.description,
                location=task.location_label or task.location_address,
                location_address=task.location_address,
                latitude=task.latitude,
                longitude=task.longitude,
                workload_minutes=task.workload_minutes,
                required_headcount=task.required_headcount,
                travel_minutes_before=task.travel_minutes_before,
                travel_minutes_after=task.travel_minutes_after,
                buffer_minutes_before=task.buffer_minutes_before,
                buffer_minutes_after=task.buffer_minutes_after,
                required_skills=[
                    {
                        "id": requirement.skill_id,
                        "code": requirement.skill.code,
                        "name": requirement.skill.name,
                        "minimum_level": requirement.minimum_level,
                        "mandatory": requirement.is_mandatory,
                    }
                    for requirement in task.skill_requirements
                    if requirement.skill
                ],
                resources=[
                    {
                        "id": assignment.resource_id,
                        "code": assignment.resource.code,
                        "name": assignment.resource.name,
                        "type": assignment.resource.resource_type,
                        "status": assignment.status,
                    }
                    for assignment in task.resource_assignments
                    if assignment.resource
                ],
            )
        )

    activities = (
        db.query(models.CRMActivity)
        .options(
            selectinload(models.CRMActivity.assigned_user),
            selectinload(models.CRMActivity.client),
            selectinload(models.CRMActivity.opportunity),
        )
        .filter(
            models.CRMActivity.due_at >= start_at,
            models.CRMActivity.due_at < end_at,
            models.CRMActivity.status != models.CRMActivityStatus.CANCELLED.value,
        )
        .all()
    )
    for activity in activities:
        events.append(
            _event(
                "CRM_ACTIVITY",
                activity.id,
                "CRM",
                activity.subject,
                activity.due_at,
                end_at=activity.due_at + timedelta(minutes=30),
                status=activity.status,
                owner_id=activity.assigned_user_id,
                owner_name=_display_user(activity.assigned_user),
                reference=activity.opportunity_reference,
                client_name=activity.client_name,
                source_view="crm",
                source_url="/manager?view=crm",
                subtitle=activity.note,
            )
        )

    milestones = (
        db.query(models.CRMOpportunity)
        .options(
            selectinload(models.CRMOpportunity.client),
            selectinload(models.CRMOpportunity.owner),
        )
        .filter(
            models.CRMOpportunity.next_milestone_at >= start_at,
            models.CRMOpportunity.next_milestone_at < end_at,
            models.CRMOpportunity.stage.notin_(
                [
                    models.CRMOpportunityStage.WON.value,
                    models.CRMOpportunityStage.LOST.value,
                ]
            ),
        )
        .all()
    )
    for opportunity in milestones:
        events.append(
            _event(
                "CRM_MILESTONE",
                opportunity.id,
                "CRM",
                opportunity.next_milestone or f"Suivi {opportunity.reference}",
                opportunity.next_milestone_at,
                end_at=opportunity.next_milestone_at + timedelta(minutes=45),
                status=opportunity.stage,
                owner_id=opportunity.owner_user_id,
                owner_name=opportunity.owner_name,
                reference=opportunity.reference,
                client_name=opportunity.client_name,
                source_view="crm",
                source_url="/manager?view=crm",
                subtitle=opportunity.title,
            )
        )

    reminder_plans = (
        db.query(models.CRMReminderPlan)
        .options(
            selectinload(models.CRMReminderPlan.assigned_user),
            selectinload(models.CRMReminderPlan.client),
            selectinload(models.CRMReminderPlan.opportunity),
        )
        .filter(
            models.CRMReminderPlan.due_at >= start_at,
            models.CRMReminderPlan.due_at < end_at,
            models.CRMReminderPlan.status == "PENDING",
        )
        .all()
    )
    for plan in reminder_plans:
        events.append(
            _event(
                "CRM_REMINDER",
                plan.id,
                "REMINDER",
                f"Relance {plan.opportunity_reference or plan.client_name}",
                plan.due_at,
                end_at=plan.due_at + timedelta(minutes=20),
                status=plan.status,
                owner_id=plan.assigned_user_id,
                owner_name=_display_user(plan.assigned_user),
                reference=plan.opportunity_reference,
                client_name=plan.client_name,
                source_view="crm",
                source_url="/manager?view=crm",
                subtitle=plan.stage_snapshot,
            )
        )

    mission_query = (
        db.query(models.MeasureMission)
        .options(
            selectinload(models.MeasureMission.assigned_user),
            selectinload(models.MeasureMission.client),
            selectinload(models.MeasureMission.site),
        )
        .filter(
            models.MeasureMission.status
            != models.MeasureMissionStatus.CANCELLED.value
        )
    )
    missions = mission_query.filter(
        models.MeasureMission.scheduled_start >= start_at,
        models.MeasureMission.scheduled_start < end_at,
    ).all()
    for mission in missions:
        events.append(
            _event(
                "MEASURE_MISSION",
                mission.id,
                "MEASURE",
                f"Métré {mission.reference}",
                mission.scheduled_start,
                end_at=_default_end(
                    mission.scheduled_start,
                    mission.scheduled_end,
                    120,
                ),
                status=mission.status,
                owner_id=mission.assigned_user_id,
                owner_name=_display_user(mission.assigned_user),
                reference=mission.reference,
                client_name=mission.client.name if mission.client else None,
                location=mission.site.formatted_address if mission.site else None,
                source_view="crm",
                source_url=f"/measure-missions/{mission.id}",
                subtitle=mission.purpose,
            )
        )
    if include_unscheduled:
        for mission in mission_query.filter(
            models.MeasureMission.scheduled_start.is_(None),
            models.MeasureMission.status.in_(
                [
                    models.MeasureMissionStatus.DRAFT.value,
                    models.MeasureMissionStatus.TO_SCHEDULE.value,
                ]
            ),
        ).all():
            unscheduled.append(
                _event(
                    "MEASURE_MISSION",
                    mission.id,
                    "MEASURE",
                    f"Métré {mission.reference}",
                    None,
                    status=mission.status,
                    owner_id=mission.assigned_user_id,
                    owner_name=_display_user(mission.assigned_user),
                    reference=mission.reference,
                    client_name=mission.client.name if mission.client else None,
                    location=mission.site.formatted_address if mission.site else None,
                    source_url=f"/measure-missions/{mission.id}",
                )
            )

    planning_query = (
        db.query(models.Planning)
        .options(selectinload(models.Planning.order))
        .filter(
            models.Planning.status.notin_(
                [models.PlanningStatus.DONE, models.PlanningStatus.DEFECT]
            )
        )
    )
    planned_work = planning_query.filter(
        models.Planning.scheduled_start >= start_at,
        models.Planning.scheduled_start < end_at,
    ).all()
    for planning in planned_work:
        assignment_key = (planning.assigned_to or "").strip().casefold()
        assigned_user = (
            users_by_username.get(assignment_key)
            or users_by_name.get(assignment_key)
        )
        events.append(
            _event(
                "WORKSHOP",
                planning.id,
                "WORKSHOP",
                f"{planning.station} · {planning.order_reference}",
                planning.scheduled_start,
                end_at=_default_end(
                    planning.scheduled_start,
                    planning.scheduled_end,
                    90,
                ),
                status=planning.status,
                owner_id=assigned_user.id if assigned_user else None,
                owner_name=_display_user(assigned_user) or planning.assigned_to,
                reference=planning.order_reference,
                client_name=planning.order.client_name if planning.order else None,
                priority="HIGH" if planning.priority and planning.priority > 5 else "NORMAL",
                source_view="orders",
                source_url="/manager?view=orders",
                subtitle=planning.issue_notes,
            )
        )
    if include_unscheduled:
        for planning in planning_query.filter(
            models.Planning.scheduled_start.is_(None)
        ).limit(200).all():
            assignment_key = (planning.assigned_to or "").strip().casefold()
            assigned_user = (
                users_by_username.get(assignment_key)
                or users_by_name.get(assignment_key)
            )
            unscheduled.append(
                _event(
                    "WORKSHOP",
                    planning.id,
                    "WORKSHOP",
                    f"{planning.station} · {planning.order_reference}",
                    None,
                    status=planning.status,
                    owner_id=assigned_user.id if assigned_user else None,
                    owner_name=_display_user(assigned_user) or planning.assigned_to,
                    reference=planning.order_reference,
                    client_name=planning.order.client_name if planning.order else None,
                    priority="HIGH" if planning.priority and planning.priority > 5 else "NORMAL",
                    source_view="orders",
                    source_url="/manager?view=orders",
                )
            )

    routes = db.query(models.DeliveryRoute).filter(
        models.DeliveryRoute.planned_date >= start_at,
        models.DeliveryRoute.planned_date < end_at,
        models.DeliveryRoute.status != "COMPLETED",
    ).all()
    for route in routes:
        driver_key = (route.driver_name or "").strip().casefold()
        assigned_user = (
            users_by_username.get(driver_key) or users_by_name.get(driver_key)
        )
        events.append(
            _event(
                "DELIVERY",
                route.id,
                "DELIVERY",
                f"Tournée {route.reference}",
                route.planned_date,
                end_at=route.planned_date + timedelta(hours=4),
                status=route.status,
                owner_id=assigned_user.id if assigned_user else None,
                owner_name=_display_user(assigned_user) or route.driver_name,
                reference=route.reference,
                location=route.vehicle,
                source_view="logistics",
                source_url="/manager?view=logistics",
            )
        )

    purchase_orders = db.query(models.PurchaseOrder).filter(
        models.PurchaseOrder.expected_date >= start_at,
        models.PurchaseOrder.expected_date < end_at,
        models.PurchaseOrder.status.notin_(
            [models.PurchaseOrderStatus.RECEIVED, models.PurchaseOrderStatus.CANCELLED]
        ),
    ).all()
    for order in purchase_orders:
        events.append(
            _event(
                "PURCHASE",
                order.id,
                "PURCHASE",
                f"Réception attendue {order.reference}",
                order.expected_date,
                end_at=order.expected_date + timedelta(hours=1),
                status=order.status,
                reference=order.reference,
                client_name=order.supplier,
                source_view="purchases",
                source_url="/manager?view=purchases",
                editable=False,
            )
        )

    absences = (
        db.query(models.UserAbsence)
        .options(selectinload(models.UserAbsence.user))
        .filter(
            models.UserAbsence.status == "APPROVED",
            models.UserAbsence.start_at < end_at,
            models.UserAbsence.end_at > start_at,
        )
        .all()
    )
    for absence in absences:
        events.append(
            _event(
                "USER_ABSENCE",
                absence.id,
                "ABSENCE",
                absence.reason or {
                    "LEAVE": "Congé",
                    "RTT": "RTT",
                    "SICK": "Arrêt maladie",
                    "TRAINING": "Formation",
                    "UNAVAILABLE": "Indisponible",
                }.get(absence.absence_type, "Indisponible"),
                absence.start_at,
                end_at=absence.end_at,
                status=absence.status,
                owner_id=absence.user_id,
                owner_name=_display_user(absence.user),
                reference=absence.absence_type,
                priority="NORMAL",
                editable=False,
                subtitle="Indisponibilité validée",
            )
        )

    selected_types = {
        value.strip().upper() for value in (types or "").split(",") if value.strip()
    }
    if selected_types:
        events = [event for event in events if event["category"] in selected_types]
        unscheduled = [
            event for event in unscheduled if event["category"] in selected_types
        ]
    if owner_id is not None:
        events = [event for event in events if event["owner_id"] == owner_id]
        unscheduled = [
            event for event in unscheduled if event["owner_id"] == owner_id
        ]

    events.sort(key=lambda event: event["start_at"] or datetime.max)
    team_load, alerts, conflict_count = _team_insights(
        events,
        unscheduled,
        active_users,
        absences,
        start_at,
        end_at,
        owner_id=owner_id,
    )
    planned_hours = round(
        sum(load["planned_hours"] for load in team_load),
        2,
    )
    capacity_hours = round(
        sum(load["capacity_hours"] for load in team_load),
        2,
    )
    utilization_pct = (
        round(planned_hours / capacity_hours * 100, 1)
        if capacity_hours
        else (100.0 if planned_hours else 0.0)
    )
    overdue_count = sum(
        1
        for event in events
        if event.get("source_type") != "USER_ABSENCE"
        and _is_overdue(event, utcnow())
    )
    return {
        "events": [_serialize_event(event) for event in events],
        "unscheduled": [_serialize_event(event) for event in unscheduled],
        "team_load": team_load,
        "alerts": [_serialize_alert(alert) for alert in alerts],
        "summary": {
            "total": len(events),
            "unscheduled": len(unscheduled),
            "conflicts": conflict_count,
            "overdue": overdue_count,
            "planned_hours": planned_hours,
            "capacity_hours": capacity_hours,
            "utilization_pct": utilization_pct,
            "overloaded_users": sum(
                1 for load in team_load if load["status"] == "OVERLOADED"
            ),
        },
        "can_edit": _has_edit_permission(db, current_user),
    }


@router.post("/tasks", status_code=201)
def create_calendar_task(
    payload: CalendarTaskCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_EDIT")),
):
    assigned_user = _active_user(db, payload.assigned_user_id)
    if payload.client_id and not db.get(models.Client, payload.client_id):
        raise HTTPException(status_code=422, detail="Client introuvable")
    if payload.opportunity_id and not db.get(
        models.CRMOpportunity, payload.opportunity_id
    ):
        raise HTTPException(status_code=422, detail="Opportunité introuvable")
    sale_order = (
        db.get(models.SaleOrder, payload.sale_order_id)
        if payload.sale_order_id
        else None
    )
    if payload.sale_order_id and not sale_order:
        raise HTTPException(status_code=422, detail="Commande signée introuvable")

    end_at = _default_end(payload.start_at, payload.end_at)
    _ensure_no_conflict(
        db,
        payload.assigned_user_id,
        payload.start_at,
        end_at,
        payload.allow_conflict,
    )
    task = models.CalendarTask(
        title=payload.title.strip(),
        description=(payload.description or "").strip() or None,
        category=payload.category,
        priority=payload.priority,
        start_at=payload.start_at,
        end_at=end_at,
        assigned_user_id=payload.assigned_user_id,
        client_id=payload.client_id,
        opportunity_id=payload.opportunity_id,
        sale_order_id=payload.sale_order_id,
        location_label=(payload.location_label or "").strip() or None,
        location_address=(payload.location_address or "").strip() or None,
        latitude=payload.latitude,
        longitude=payload.longitude,
        workload_minutes=payload.workload_minutes,
        required_headcount=payload.required_headcount,
        travel_minutes_before=payload.travel_minutes_before,
        travel_minutes_after=payload.travel_minutes_after,
        buffer_minutes_before=payload.buffer_minutes_before,
        buffer_minutes_after=payload.buffer_minutes_after,
        created_by=current_user.get("sub") or "Système",
    )
    db.add(task)
    db.flush()
    _sync_task_requirements(db, task, payload, current_user)
    _record_task_change(
        db,
        task,
        current_user,
        "CREATED",
        changes={
            "assigned_user_id": task.assigned_user_id,
            "start_at": task.start_at.isoformat(),
            "end_at": task.end_at.isoformat(),
            "skill_ids": [
                item.skill_id for item in task.skill_requirements
            ],
            "resource_ids": [
                item.resource_id for item in task.resource_assignments
            ],
        },
    )
    _notify_assignment(db, task, task.assigned_user_id, "ASSIGNMENT")
    db.commit()
    db.refresh(task)
    return _serialize_event(_event(
        "CALENDAR_TASK",
        task.id,
        task.category,
        task.title,
        task.start_at,
        end_at=task.end_at,
        status=task.status,
        owner_id=task.assigned_user_id,
        owner_name=_display_user(assigned_user),
        reference=sale_order.reference if sale_order else f"PLN-{task.id:05d}",
        client_name=sale_order.client_name if sale_order else None,
        location=task.location_label or task.location_address,
        priority=task.priority,
        subtitle=task.description,
        required_skills=[
            {
                "id": item.skill_id,
                "code": item.skill.code,
                "name": item.skill.name,
            }
            for item in task.skill_requirements
            if item.skill
        ],
        resources=[
            {
                "id": item.resource_id,
                "code": item.resource.code,
                "name": item.resource.name,
            }
            for item in task.resource_assignments
            if item.resource
        ],
    ))


@router.patch("/events/{source_type}/{source_id}")
def update_schedule_event(
    source_type: str,
    source_id: int,
    payload: ScheduleEventUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_EDIT")),
):
    source_type = source_type.upper()
    if source_type not in EDITABLE_SOURCES:
        raise HTTPException(
            status_code=409,
            detail="Cette échéance se modifie depuis son module d'origine.",
        )
    assigned_user = _active_user(db, payload.assigned_user_id)

    if source_type == "CALENDAR_TASK":
        record = db.get(models.CalendarTask, source_id)
        if not record:
            raise HTTPException(status_code=404, detail="Tâche introuvable")
        previous = {
            "start_at": record.start_at.isoformat() if record.start_at else None,
            "end_at": record.end_at.isoformat() if record.end_at else None,
            "assigned_user_id": record.assigned_user_id,
            "status": record.status,
        }
        start_at = payload.start_at or record.start_at
        end_at = payload.end_at or record.end_at or start_at + timedelta(hours=1)
        owner_id = (
            payload.assigned_user_id
            if payload.assigned_user_id is not None
            else record.assigned_user_id
        )
        _ensure_no_conflict(
            db,
            owner_id,
            start_at,
            end_at,
            payload.allow_conflict,
            exclude_source=source_type,
            exclude_id=source_id,
        )
        record.start_at = start_at
        record.end_at = end_at
        if payload.assigned_user_id is not None:
            record.assigned_user_id = payload.assigned_user_id
        if payload.status:
            status = payload.status.upper()
            if status not in TASK_STATUSES:
                raise HTTPException(status_code=422, detail="Statut de tâche invalide")
            record.status = status
        changes = {
            key: {"before": previous[key], "after": value}
            for key, value in {
                "start_at": record.start_at.isoformat() if record.start_at else None,
                "end_at": record.end_at.isoformat() if record.end_at else None,
                "assigned_user_id": record.assigned_user_id,
                "status": record.status,
            }.items()
            if previous[key] != value
        }
        if changes:
            _record_task_change(
                db,
                record,
                current_user,
                "UPDATED",
                changes=changes,
                reason=payload.change_reason or "Réorganisation du planning",
                source_screen=payload.source_screen,
            )
            if (
                previous["assigned_user_id"] != record.assigned_user_id
                or "start_at" in changes
                or "end_at" in changes
            ):
                _notify_assignment(
                    db,
                    record,
                    record.assigned_user_id,
                    "UPDATED",
                )

    elif source_type == "MEASURE_MISSION":
        record = db.get(models.MeasureMission, source_id)
        if not record:
            raise HTTPException(status_code=404, detail="Mission de métré introuvable")
        start_at = payload.start_at or record.scheduled_start
        if not start_at:
            raise HTTPException(status_code=422, detail="Date de début requise")
        end_at = payload.end_at or record.scheduled_end or start_at + timedelta(hours=2)
        owner_id = (
            payload.assigned_user_id
            if payload.assigned_user_id is not None
            else record.assigned_user_id
        )
        _ensure_no_conflict(
            db,
            owner_id,
            start_at,
            end_at,
            payload.allow_conflict,
            exclude_source=source_type,
            exclude_id=source_id,
        )
        record.scheduled_start = start_at
        record.scheduled_end = end_at
        if payload.assigned_user_id is not None:
            record.assigned_user_id = payload.assigned_user_id
        if record.status in {
            models.MeasureMissionStatus.DRAFT.value,
            models.MeasureMissionStatus.TO_SCHEDULE.value,
        }:
            record.status = models.MeasureMissionStatus.SCHEDULED.value

    elif source_type == "CRM_ACTIVITY":
        record = db.get(models.CRMActivity, source_id)
        if not record:
            raise HTTPException(status_code=404, detail="Action CRM introuvable")
        start_at = payload.start_at or record.due_at
        if not start_at:
            raise HTTPException(status_code=422, detail="Échéance requise")
        end_at = payload.end_at or start_at + timedelta(minutes=30)
        owner_id = (
            payload.assigned_user_id
            if payload.assigned_user_id is not None
            else record.assigned_user_id
        )
        _ensure_no_conflict(
            db,
            owner_id,
            start_at,
            end_at,
            payload.allow_conflict,
            exclude_source=source_type,
            exclude_id=source_id,
        )
        record.due_at = start_at
        if payload.assigned_user_id is not None:
            record.assigned_user_id = payload.assigned_user_id
        if payload.status:
            if payload.status not in {
                models.CRMActivityStatus.TODO.value,
                models.CRMActivityStatus.COMPLETED.value,
                models.CRMActivityStatus.CANCELLED.value,
            }:
                raise HTTPException(status_code=422, detail="Statut CRM invalide")
            record.status = payload.status
            if payload.status == models.CRMActivityStatus.COMPLETED.value:
                record.completed_at = utcnow()

    elif source_type == "CRM_MILESTONE":
        record = db.get(models.CRMOpportunity, source_id)
        if not record:
            raise HTTPException(status_code=404, detail="Opportunité introuvable")
        start_at = payload.start_at or record.next_milestone_at
        if not start_at:
            raise HTTPException(status_code=422, detail="Échéance requise")
        end_at = payload.end_at or start_at + timedelta(minutes=45)
        owner_id = (
            payload.assigned_user_id
            if payload.assigned_user_id is not None
            else record.owner_user_id
        )
        _ensure_no_conflict(
            db,
            owner_id,
            start_at,
            end_at,
            payload.allow_conflict,
            exclude_source=source_type,
            exclude_id=source_id,
        )
        record.next_milestone_at = start_at
        if payload.assigned_user_id is not None:
            record.owner_user_id = payload.assigned_user_id

    elif source_type == "CRM_REMINDER":
        record = db.get(models.CRMReminderPlan, source_id)
        if not record:
            raise HTTPException(status_code=404, detail="Relance introuvable")
        start_at = payload.start_at or record.due_at
        if not start_at:
            raise HTTPException(status_code=422, detail="Échéance requise")
        end_at = payload.end_at or start_at + timedelta(minutes=20)
        owner_id = (
            payload.assigned_user_id
            if payload.assigned_user_id is not None
            else record.assigned_user_id
        )
        _ensure_no_conflict(
            db,
            owner_id,
            start_at,
            end_at,
            payload.allow_conflict,
            exclude_source=source_type,
            exclude_id=source_id,
        )
        record.due_at = start_at
        if payload.assigned_user_id is not None:
            record.assigned_user_id = payload.assigned_user_id

    elif source_type == "WORKSHOP":
        record = db.get(models.Planning, source_id)
        if not record:
            raise HTTPException(status_code=404, detail="Tâche atelier introuvable")
        start_at = payload.start_at or record.scheduled_start
        if not start_at:
            raise HTTPException(status_code=422, detail="Date de début requise")
        end_at = payload.end_at or record.scheduled_end or start_at + timedelta(minutes=90)
        owner = assigned_user or _active_user_by_name(db, record.assigned_to)
        _ensure_no_conflict(
            db,
            owner.id if owner else None,
            start_at,
            end_at,
            payload.allow_conflict,
            exclude_source=source_type,
            exclude_id=source_id,
        )
        if payload.assigned_user_id is not None:
            record.assigned_to = assigned_user.username
        record.scheduled_start = start_at
        record.scheduled_end = end_at

    elif source_type == "DELIVERY":
        record = db.get(models.DeliveryRoute, source_id)
        if not record:
            raise HTTPException(status_code=404, detail="Tournée introuvable")
        start_at = payload.start_at or record.planned_date
        if not start_at:
            raise HTTPException(status_code=422, detail="Date de tournée requise")
        end_at = payload.end_at or start_at + timedelta(hours=4)
        owner = assigned_user or _active_user_by_name(db, record.driver_name)
        _ensure_no_conflict(
            db,
            owner.id if owner else None,
            start_at,
            end_at,
            payload.allow_conflict,
            exclude_source=source_type,
            exclude_id=source_id,
        )
        if payload.assigned_user_id is not None:
            record.driver_name = _display_user(assigned_user)
        record.planned_date = start_at

    db.commit()
    return {"status": "updated", "source_type": source_type, "source_id": source_id}


@router.get("/events/{source_type}/{source_id}/execution")
def get_schedule_execution(
    source_type: str,
    source_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_VIEW")),
):
    source_type = source_type.upper()
    record, owner_id, title, source_url = _execution_source(
        db,
        source_type,
        source_id,
    )
    state = (
        db.query(models.ScheduleExecutionState)
        .options(selectinload(models.ScheduleExecutionState.assigned_user))
        .filter(
            models.ScheduleExecutionState.source_type == source_type,
            models.ScheduleExecutionState.source_id == source_id,
        )
        .first()
    )
    current_record = _current_user_record(db, current_user)
    responsible_id = state.assigned_user_id if state else owner_id
    can_manage = _has_edit_permission(db, current_user)
    can_execute = bool(
        can_manage
        or (
            current_record
            and responsible_id
            and current_record.id == responsible_id
        )
    )
    history = []
    if state:
        history = (
            db.query(models.ScheduleExecutionLog)
            .filter(models.ScheduleExecutionLog.state_id == state.id)
            .order_by(models.ScheduleExecutionLog.created_at.desc())
            .limit(100)
            .all()
        )
    return _execution_payload(
        state,
        source_type=source_type,
        source_id=source_id,
        owner_id=owner_id,
        title=title,
        source_url=source_url,
        initial_status=_initial_execution_status(source_type, record),
        can_execute=can_execute,
        can_manage=can_manage,
        history=history,
    )


@router.post("/events/{source_type}/{source_id}/execute")
def transition_schedule_execution(
    source_type: str,
    source_id: int,
    payload: ScheduleExecutionTransition,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_VIEW")),
):
    source_type = source_type.upper()
    record, owner_id, title, source_url = _execution_source(
        db,
        source_type,
        source_id,
    )
    current_record = _current_user_record(db, current_user)
    can_manage = _has_edit_permission(db, current_user)
    state = (
        db.query(models.ScheduleExecutionState)
        .options(selectinload(models.ScheduleExecutionState.assigned_user))
        .filter(
            models.ScheduleExecutionState.source_type == source_type,
            models.ScheduleExecutionState.source_id == source_id,
        )
        .first()
    )
    responsible_id = state.assigned_user_id if state else owner_id
    if not can_manage and (
        not current_record
        or not responsible_id
        or current_record.id != responsible_id
    ):
        raise HTTPException(
            status_code=403,
            detail="Cette tâche doit être exécutée par son responsable.",
        )

    target_user_id = (
        payload.assigned_user_id
        if payload.assigned_user_id is not None
        else responsible_id
    )
    if payload.assigned_user_id is not None and not can_manage:
        if not current_record or payload.assigned_user_id != current_record.id:
            raise HTTPException(
                status_code=403,
                detail="La réaffectation nécessite le droit de modifier le planning.",
            )
    target_user = _active_user(db, target_user_id)
    execution_reason = _resolve_execution_reason(
        db,
        action=payload.action,
        reason_code=payload.reason_code,
        comment=payload.reason,
    )
    synchronized_reason = (
        " · ".join(
            part
            for part in [
                execution_reason.label if execution_reason else None,
                payload.reason,
            ]
            if part
        )
        or None
    )

    now = utcnow()
    actor_id, actor_name = _actor_identity(db, current_user)
    if not state:
        state = models.ScheduleExecutionState(
            source_type=source_type,
            source_id=source_id,
            status=_initial_execution_status(source_type, record),
            assigned_user_id=target_user_id,
            updated_by_user_id=actor_id,
            updated_by_name=actor_name,
        )
        db.add(state)
        db.flush()

    previous_status = state.status
    if previous_status not in EXECUTION_TRANSITIONS[payload.action]:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Transition {payload.action} impossible depuis "
                f"le statut {previous_status}."
            ),
        )

    previous_responsible_id = state.assigned_user_id
    state.elapsed_minutes = _execution_elapsed_minutes(state, now)
    state.active_since = None
    state.assigned_user_id = target_user_id
    if payload.action == "START":
        state.status = "IN_PROGRESS"
        state.started_at = state.started_at or now
        state.active_since = now
        state.completed_at = None
    elif payload.action == "PAUSE":
        state.status = "PAUSED"
    elif payload.action == "BLOCK":
        state.status = "BLOCKED"
    elif payload.action == "COMPLETE":
        state.status = "DONE"
        state.completed_at = now

    if payload.time_spent_minutes is not None:
        state.elapsed_minutes = payload.time_spent_minutes
    state.last_reason_code = execution_reason.code if execution_reason else None
    state.last_reason_label = execution_reason.label if execution_reason else None
    state.last_reason = payload.reason
    state.last_note = payload.note
    state.updated_by_user_id = actor_id
    state.updated_by_name = actor_name
    _assign_execution_source(source_type, record, target_user)
    _sync_execution_source(
        db,
        source_type,
        record,
        state.status,
        synchronized_reason,
    )
    db.add(
        models.ScheduleExecutionLog(
            state_id=state.id,
            action=payload.action,
            previous_status=previous_status,
            current_status=state.status,
            reason_code=execution_reason.code if execution_reason else None,
            reason_label=execution_reason.label if execution_reason else None,
            reason=payload.reason,
            note=payload.note,
            elapsed_minutes=state.elapsed_minutes,
            responsible_user_id=state.assigned_user_id,
            actor_user_id=actor_id,
            actor_name=actor_name,
            source_screen=payload.source_screen,
        )
    )
    task_id = source_id if source_type == "CALENDAR_TASK" else None
    _notify_execution(
        db,
        source_type=source_type,
        source_id=source_id,
        task_id=task_id,
        user_id=state.assigned_user_id,
        title=title,
        action=payload.action,
        actor_name=actor_name,
    )
    if (
        previous_responsible_id
        and previous_responsible_id != state.assigned_user_id
    ):
        _notify_execution(
            db,
            source_type=source_type,
            source_id=source_id,
            task_id=task_id,
            user_id=previous_responsible_id,
            title=title,
            action=payload.action,
            actor_name=actor_name,
        )
    if payload.action == "BLOCK":
        db.flush()
        evaluate_operational_alerts(db, now=now)
    elif payload.action in {"START", "COMPLETE"}:
        auto_resolve_incidents(
            db,
            source_type=source_type,
            source_id=source_id,
            action=payload.action,
            actor_user_id=actor_id,
            actor_name=actor_name,
        )
    db.commit()
    db.refresh(state)
    history = (
        db.query(models.ScheduleExecutionLog)
        .filter(models.ScheduleExecutionLog.state_id == state.id)
        .order_by(models.ScheduleExecutionLog.created_at.desc())
        .limit(100)
        .all()
    )
    return _execution_payload(
        state,
        source_type=source_type,
        source_id=source_id,
        owner_id=owner_id,
        title=title,
        source_url=source_url,
        initial_status=state.status,
        can_execute=True,
        can_manage=can_manage,
        history=history,
    )


@router.delete("/tasks/{task_id}", status_code=204)
def cancel_calendar_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_EDIT")),
):
    task = db.get(models.CalendarTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tâche introuvable")
    task.status = "CANCELLED"
    _record_task_change(
        db,
        task,
        current_user,
        "CANCELLED",
        reason="Annulation depuis le planning",
    )
    _notify_assignment(db, task, task.assigned_user_id, "UPDATED")
    db.commit()
    return None


@router.get("/tasks/{task_id}/history")
def get_calendar_task_history(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_VIEW")),
):
    if not db.get(models.CalendarTask, task_id):
        raise HTTPException(status_code=404, detail="Tâche introuvable")
    return (
        db.query(models.PlanningChangeLog)
        .filter(models.PlanningChangeLog.task_id == task_id)
        .order_by(models.PlanningChangeLog.created_at.desc())
        .all()
    )


@router.get("/notifications")
def get_planning_notifications(
    unread_only: bool = False,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_VIEW")),
):
    user = _current_user_record(db, current_user)
    if not user:
        raise HTTPException(status_code=403, detail="Utilisateur introuvable")
    evaluate_operational_alerts(db)
    db.commit()
    query = db.query(models.PlanningNotification).filter(
        models.PlanningNotification.user_id == user.id
    )
    if unread_only:
        query = query.filter(models.PlanningNotification.status == "UNREAD")
    return query.order_by(models.PlanningNotification.created_at.desc()).limit(100).all()


@router.patch("/notifications/{notification_id}/read")
def mark_planning_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_VIEW")),
):
    user = _current_user_record(db, current_user)
    notification = db.get(models.PlanningNotification, notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification introuvable")
    if not user or notification.user_id != user.id:
        raise HTTPException(status_code=403, detail="Notification non accessible")
    notification.status = "READ"
    notification.read_at = utcnow()
    db.commit()
    return {"status": "read"}

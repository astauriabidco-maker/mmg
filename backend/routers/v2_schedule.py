from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, selectinload

from .. import models
from ..core.security import (
    require_permissions,
    roles_have_permission,
)
from ..core.time import utcnow
from ..database import get_db


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
TASK_STATUSES = {"TODO", "IN_PROGRESS", "DONE", "CANCELLED"}
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
    allow_conflict: bool = False

    @model_validator(mode="after")
    def validate_values(self):
        self.start_at = _naive_utc(self.start_at)
        self.end_at = _naive_utc(self.end_at)
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValueError("La fin doit être postérieure au début")
        return self


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
):
    return {
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


def _has_edit_permission(db: Session, current_user: dict) -> bool:
    permissions = current_user.get("permissions") or []
    if "*" in permissions or "PLANNING_EDIT" in permissions:
        return True
    role_names = current_user.get("roles") or [current_user.get("role")]
    return roles_have_permission(
        db,
        [role for role in role_names if role],
        "PLANNING_EDIT",
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
    users = (
        db.query(models.User)
        .filter(models.User.is_active == True)  # noqa: E712
        .order_by(models.User.first_name, models.User.last_name, models.User.username)
        .all()
    )
    absences = (
        db.query(models.UserAbsence)
        .filter(
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
        "can_edit": _has_edit_permission(db, current_user),
        "timezone": "Europe/Paris",
    }


@router.put("/availability/{user_id}")
def update_user_availability(
    user_id: int,
    payload: WorkScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_EDIT")),
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
    current_user: dict = Depends(require_permissions("PLANNING_EDIT")),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    overlapping = (
        db.query(models.UserAbsence)
        .filter(
            models.UserAbsence.user_id == user_id,
            models.UserAbsence.status == "APPROVED",
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
        status="APPROVED",
        reason=payload.reason,
        created_by=current_user.get("sub") or "planning",
    )
    db.add(absence)
    db.commit()
    db.refresh(absence)
    return _serialize_absence(absence)


@router.delete("/availability/absences/{absence_id}")
def delete_user_absence(
    absence_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permissions("PLANNING_EDIT")),
):
    absence = (
        db.query(models.UserAbsence)
        .filter(models.UserAbsence.id == absence_id)
        .first()
    )
    if not absence:
        raise HTTPException(status_code=404, detail="Indisponibilité introuvable")
    db.delete(absence)
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
    users = (
        db.query(models.User)
        .filter(models.User.is_active == True)  # noqa: E712
        .order_by(models.User.first_name, models.User.last_name, models.User.username)
        .all()
    )
    clients = (
        db.query(models.Client)
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
        "clients": [{"id": client.id, "name": client.name} for client in clients],
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
        "can_edit": _has_edit_permission(db, current_user),
    }


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
        created_by=current_user.get("sub") or "Système",
    )
    db.add(task)
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
        priority=task.priority,
        subtitle=task.description,
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
    db.commit()
    return None

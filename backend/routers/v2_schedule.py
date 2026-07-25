from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

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
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValueError("La fin doit être postérieure au début")
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
            serialized[field] = f"{value.isoformat()}Z"
    return serialized


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
    conflicts = []

    task_query = db.query(models.CalendarTask).filter(
        models.CalendarTask.assigned_user_id == assigned_user_id,
        models.CalendarTask.status != "CANCELLED",
        _overlaps(
            models.CalendarTask.start_at,
            models.CalendarTask.end_at,
            start_at,
            end_at,
        ),
    )
    if exclude_source == "CALENDAR_TASK" and exclude_id:
        task_query = task_query.filter(models.CalendarTask.id != exclude_id)
    for task in task_query.all():
        conflicts.append(
            _event(
                "CALENDAR_TASK",
                task.id,
                task.category,
                task.title,
                task.start_at,
                end_at=_default_end(task.start_at, task.end_at),
                status=task.status,
                reference=f"PLN-{task.id:05d}",
            )
        )

    mission_query = db.query(models.MeasureMission).filter(
        models.MeasureMission.assigned_user_id == assigned_user_id,
        models.MeasureMission.status != models.MeasureMissionStatus.CANCELLED.value,
        _overlaps(
            models.MeasureMission.scheduled_start,
            models.MeasureMission.scheduled_end,
            start_at,
            end_at,
        ),
    )
    if exclude_source == "MEASURE_MISSION" and exclude_id:
        mission_query = mission_query.filter(models.MeasureMission.id != exclude_id)
    for mission in mission_query.all():
        conflicts.append(
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
                reference=mission.reference,
            )
        )

    activity_query = db.query(models.CRMActivity).filter(
        models.CRMActivity.assigned_user_id == assigned_user_id,
        models.CRMActivity.status == models.CRMActivityStatus.TODO.value,
        models.CRMActivity.due_at >= start_at,
        models.CRMActivity.due_at < end_at,
    )
    if exclude_source == "CRM_ACTIVITY" and exclude_id:
        activity_query = activity_query.filter(models.CRMActivity.id != exclude_id)
    for activity in activity_query.all():
        conflicts.append(
            _event(
                "CRM_ACTIVITY",
                activity.id,
                "CRM",
                activity.subject,
                activity.due_at,
                end_at=activity.due_at + timedelta(minutes=30),
                status=activity.status,
            )
        )
    return conflicts


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
    if end_at <= start_at:
        raise HTTPException(status_code=422, detail="Période invalide")
    if end_at - start_at > timedelta(days=124):
        raise HTTPException(status_code=422, detail="La période est limitée à 124 jours")

    events = []
    unscheduled = []

    tasks = db.query(models.CalendarTask).filter(
        models.CalendarTask.status != "CANCELLED",
        _overlaps(
            models.CalendarTask.start_at,
            models.CalendarTask.end_at,
            start_at,
            end_at,
        ),
    ).all()
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

    activities = db.query(models.CRMActivity).filter(
        models.CRMActivity.due_at >= start_at,
        models.CRMActivity.due_at < end_at,
        models.CRMActivity.status != models.CRMActivityStatus.CANCELLED.value,
    ).all()
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

    milestones = db.query(models.CRMOpportunity).filter(
        models.CRMOpportunity.next_milestone_at >= start_at,
        models.CRMOpportunity.next_milestone_at < end_at,
        models.CRMOpportunity.stage.notin_(
            [
                models.CRMOpportunityStage.WON.value,
                models.CRMOpportunityStage.LOST.value,
            ]
        ),
    ).all()
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

    reminder_plans = db.query(models.CRMReminderPlan).filter(
        models.CRMReminderPlan.due_at >= start_at,
        models.CRMReminderPlan.due_at < end_at,
        models.CRMReminderPlan.status == "PENDING",
    ).all()
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

    mission_query = db.query(models.MeasureMission).filter(
        models.MeasureMission.status != models.MeasureMissionStatus.CANCELLED.value
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

    planning_query = db.query(models.Planning).filter(
        models.Planning.status.notin_(
            [models.PlanningStatus.DONE, models.PlanningStatus.DEFECT]
        )
    )
    planned_work = planning_query.filter(
        models.Planning.scheduled_start >= start_at,
        models.Planning.scheduled_start < end_at,
    ).all()
    users_by_username = {
        user.username: user
        for user in db.query(models.User)
        .filter(models.User.is_active == True)  # noqa: E712
        .all()
    }
    for planning in planned_work:
        assigned_user = users_by_username.get(planning.assigned_to)
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
            assigned_user = users_by_username.get(planning.assigned_to)
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
        events.append(
            _event(
                "DELIVERY",
                route.id,
                "DELIVERY",
                f"Tournée {route.reference}",
                route.planned_date,
                end_at=route.planned_date + timedelta(hours=4),
                status=route.status,
                reference=route.reference,
                owner_name=route.driver_name,
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
    return {
        "events": [_serialize_event(event) for event in events],
        "unscheduled": [_serialize_event(event) for event in unscheduled],
        "summary": {
            "total": len(events),
            "unscheduled": len(unscheduled),
            "conflicts": 0,
            "overdue": sum(
                1
                for event in events
                if event["start_at"] < utcnow()
                and event["status"] not in {"DONE", "termine", "COMPLETED"}
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

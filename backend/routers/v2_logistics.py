from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import datetime
import os

from ..database import get_db
from .. import models, schemas
from ..core import security, uploads
from ..core.time import utcnow

router = APIRouter(
    prefix="/v2/logistics",
    tags=["logistics"],
    dependencies=[Depends(security.get_current_user)],
)

FINAL_NOTE_STATUSES = {"DELIVERED", "RETURNED", "CANCELLED"}


def _serialize_queue_item(note: models.DeliveryNote) -> dict:
    route = note.route
    status = note.status or "READY"
    blockers: list[str] = []
    signals: list[str] = []
    today = utcnow().date()

    if not (note.delivery_address or "").strip():
        blockers.append("ADDRESS_MISSING")
    if not (note.contact_phone or "").strip():
        signals.append("CONTACT_MISSING")
    if route:
        signals.append(f"ROUTE_{route.status or 'UNKNOWN'}")
        if (
            route.planned_date
            and route.planned_date.date() < today
            and status not in FINAL_NOTE_STATUSES
        ):
            blockers.append("LATE_DELIVERY")
    else:
        signals.append("NEEDS_ROUTE")

    if status in {"ISSUE", "RETURNED"}:
        next_action = "HANDLE_ISSUE"
        priority = "CRITICAL"
    elif blockers:
        next_action = "COMPLETE_DELIVERY_INFO"
        priority = "CRITICAL"
    elif status == "READY":
        next_action = "ASSIGN_ROUTE"
        priority = "URGENT"
    elif status == "ASSIGNED":
        next_action = "START_ROUTE"
        priority = "TO_PLAN"
    elif status == "IN_TRANSIT":
        next_action = "COLLECT_SIGNATURE"
        priority = "URGENT"
    elif status == "DELIVERED" and not note.signed_at:
        next_action = "ARCHIVE_PROOF"
        priority = "TO_PLAN"
    else:
        next_action = "CLOSE"
        priority = "DONE"

    if note.signed_at:
        signals.append("SIGNED")

    return {
        "note_id": note.id,
        "reference": note.reference,
        "client_name": note.client_name,
        "delivery_address": note.delivery_address,
        "contact_phone": note.contact_phone,
        "status": status,
        "route_id": route.id if route else None,
        "route_reference": route.reference if route else None,
        "route_status": route.status if route else None,
        "planned_date": route.planned_date.isoformat() if route and route.planned_date else None,
        "driver_name": route.driver_name if route else None,
        "sale_order_id": note.sale_order_id,
        "order_id": note.order_id,
        "signed_at": note.signed_at.isoformat() if note.signed_at else None,
        "signature_path": note.signature_path,
        "next_action": next_action,
        "priority": priority,
        "blockers": blockers,
        "signals": signals,
    }


def _queue_sort_key(item: dict) -> tuple[int, str]:
    priority_rank = {
        "CRITICAL": 0,
        "URGENT": 1,
        "TO_PLAN": 2,
        "DONE": 3,
    }
    return priority_rank.get(item["priority"], 9), item.get("reference") or ""


def generate_route_ref(db: Session):
    year = utcnow().year
    count = db.query(models.DeliveryRoute).filter(models.DeliveryRoute.reference.like(f"ROUTE-{year}-%")).count()
    return f"ROUTE-{year}-{count + 1:04d}"

@router.get("/routes", response_model=List[schemas.DeliveryRouteResponse])
def get_routes(db: Session = Depends(get_db)):
    return db.query(models.DeliveryRoute).order_by(models.DeliveryRoute.planned_date.asc()).all()


@router.get("/queue")
def get_logistics_queue(db: Session = Depends(get_db)):
    notes = (
        db.query(models.DeliveryNote)
        .options(joinedload(models.DeliveryNote.route))
        .order_by(models.DeliveryNote.id.desc())
        .all()
    )
    routes = db.query(models.DeliveryRoute).all()
    items = sorted((_serialize_queue_item(note) for note in notes), key=_queue_sort_key)
    summary = {
        "total_notes": len(items),
        "ready_count": sum(1 for item in items if item["status"] == "READY"),
        "assigned_count": sum(1 for item in items if item["status"] == "ASSIGNED"),
        "in_transit_count": sum(1 for item in items if item["status"] == "IN_TRANSIT"),
        "delivered_count": sum(1 for item in items if item["status"] == "DELIVERED"),
        "issue_count": sum(1 for item in items if item["status"] in {"ISSUE", "RETURNED"}),
        "blocked_count": sum(1 for item in items if item["blockers"]),
        "needs_route_count": sum(1 for item in items if item["next_action"] == "ASSIGN_ROUTE"),
        "proof_missing_count": sum(1 for item in items if item["next_action"] == "ARCHIVE_PROOF"),
        "planned_routes": sum(1 for route in routes if route.status == "PLANNED"),
        "in_transit_routes": sum(1 for route in routes if route.status == "IN_TRANSIT"),
        "completed_routes": sum(1 for route in routes if route.status == "COMPLETED"),
    }
    return {
        "summary": summary,
        "items": items,
    }

@router.post("/routes", response_model=schemas.DeliveryRouteResponse)
def create_route(route: schemas.DeliveryRouteCreate, db: Session = Depends(get_db), role: str = Depends(security.get_current_user_role)):
    if role not in ["ADMIN", "MANAGER"]:
        raise HTTPException(status_code=403, detail="Non autorisé")

    new_route = models.DeliveryRoute(
        reference=generate_route_ref(db),
        driver_name=route.driver_name,
        vehicle=route.vehicle,
        planned_date=route.planned_date,
        status="PLANNED"
    )
    db.add(new_route)
    db.flush()

    # Assign notes
    if route.note_ids:
        notes = db.query(models.DeliveryNote).filter(models.DeliveryNote.id.in_(route.note_ids)).all()
        for note in notes:
            note.route_id = new_route.id
            note.status = "ASSIGNED"
            
    db.commit()
    db.refresh(new_route)
    return new_route

@router.get("/notes/ready", response_model=List[schemas.DeliveryNoteResponse])
def get_ready_notes(db: Session = Depends(get_db)):
    return db.query(models.DeliveryNote).filter(models.DeliveryNote.status == "READY").all()

@router.post("/notes/{note_id}/deliver", response_model=schemas.DeliveryNoteResponse)
def mark_delivered(note_id: int, payload: Optional[schemas.DeliveryConfirmRequest] = None, db: Session = Depends(get_db)):
    # Confirmation de livraison depuis l'app chauffeur (signature client)
    note = db.query(models.DeliveryNote).filter(models.DeliveryNote.id == note_id).first()
    if not note:
        raise HTTPException(404, "BL non trouvé")
        
    note.status = "DELIVERED"
    note.signed_at = utcnow()
    
    # Persiste la signature client (base64) sous uploads/delivery/ — même
    # pipeline allowlisté/borné que les autres uploads (backend/core/uploads.py).
    if payload and payload.signature_image:
        content, extension = uploads.decode_base64_upload(payload.signature_image)
        directory = os.path.join("uploads", "delivery")
        os.makedirs(directory, exist_ok=True)
        filename = uploads.generate_safe_filename(extension, prefix="sig_")
        file_path = os.path.join(directory, filename)
        with open(file_path, "wb") as signature_file:
            signature_file.write(content)
        note.signature_path = file_path.replace(os.sep, "/")
    
    # Check if route is fully delivered
    if note.route_id:
        route = db.query(models.DeliveryRoute).filter(models.DeliveryRoute.id == note.route_id).first()
        if route:
            all_delivered = all(n.status == "DELIVERED" for n in route.notes)
            if all_delivered:
                route.status = "COMPLETED"
                
    db.commit()
    db.refresh(note)
    return note

@router.post("/routes/{route_id}/start")
def start_route(route_id: int, db: Session = Depends(get_db)):
    route = db.query(models.DeliveryRoute).filter(models.DeliveryRoute.id == route_id).first()
    if not route:
        raise HTTPException(404, "Tournée non trouvée")
    route.status = "IN_TRANSIT"
    for note in route.notes:
        if note.status == "ASSIGNED":
            note.status = "IN_TRANSIT"
    db.commit()
    return {"status": "success"}

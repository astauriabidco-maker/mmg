from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
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

def generate_route_ref(db: Session):
    year = utcnow().year
    count = db.query(models.DeliveryRoute).filter(models.DeliveryRoute.reference.like(f"ROUTE-{year}-%")).count()
    return f"ROUTE-{year}-{count + 1:04d}"

@router.get("/routes", response_model=List[schemas.DeliveryRouteResponse])
def get_routes(db: Session = Depends(get_db)):
    return db.query(models.DeliveryRoute).order_by(models.DeliveryRoute.planned_date.asc()).all()

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

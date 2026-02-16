from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
import os
import base64
import uuid
from datetime import datetime
from ..database import get_db
from .. import models, schemas

router = APIRouter(prefix="/v2/mmg", tags=["mmg"])

# Helper to save base64 image
def save_base64_image(base64_str: str, folder: str, prefix: str):
    try:
        if "base64," in base64_str:
            base64_str = base64_str.split("base64,")[1]
        
        img_data = base64.b64decode(base64_str)
        filename = f"{prefix}_{uuid.uuid4().hex[:8]}.png"
        filepath = os.path.join("backend/static/mmg", folder, filename)
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "wb") as f:
            f.write(img_data)
        
        return f"/static/mmg/{folder}/{filename}"
    except Exception as e:
        print(f"Error saving image: {e}")
        return None

def generate_reference(db: Session):
    year = datetime.utcnow().year
    prefix = f"MMG-{year}-"
    
    # Count existing for this year
    count = db.query(models.MMG).filter(models.MMG.reference.like(f"{prefix}%")).count()
    new_id = count + 1
    return f"{prefix}{str(new_id).zfill(5)}"

@router.post("/", response_model=schemas.MMGResponse)
async def create_dossier(item: schemas.MMGCreate, db: Session = Depends(get_db)):
    # 1. Generate Reference
    ref = generate_reference(db)
    
    # 2. Save Signature
    sig_path = save_base64_image(item.signature, "signatures", "sig")
    
    # 3. Save Photos (assume they might be base64 if list of strings)
    photo_paths = []
    for i, p_base64 in enumerate(item.photos):
        path = save_base64_image(p_base64, "photos", f"photo_{i}")
        if path:
            photo_paths.append(path)
    
    # 4. Create Model
    db_item = models.MMG(
        reference=ref,
        client_name=item.client.name,
        client_contact=item.client.contact,
        client_address=item.client.address,
        site_address=item.client.site_address,
        client_email=item.client.email,
        client_type=item.client.client_type,
        
        width=item.measurements.width_mm,
        height=item.measurements.height_mm,
        passage_height=item.measurements.passage_height_mm,
        
        sill_height=item.options.sill_height_mm,
        transom_height=item.options.transom_height_mm,
        shutter_type=item.options.shutter_type,
        
        view_type=item.configuration.view,
        opening_type=item.configuration.opening_type,
        opening_side=item.configuration.opening_side,
        sash_count=item.configuration.sash_count,
        
        material=item.configuration.material,
        product_series=item.configuration.product_series,
        color_ral=item.configuration.color_ral,
        is_bicolor=item.configuration.is_bicolor,
        texture=item.configuration.texture,
        glazing_type=item.configuration.glazing_type,
        installation_type=item.configuration.installation_type,
        hardware_type=item.configuration.hardware_type,
        is_pmr_compliant=item.configuration.is_pmr_compliant,
        doublage_thickness=item.configuration.doublage_thickness,
        keep_existing_frame=item.configuration.keep_existing_frame,
        
        floor_number=item.logistics.floor_number if item.logistics else 0,
        access_difficulty=item.logistics.access_difficulty if item.logistics else "Standard",
        environment=item.logistics.environment if item.logistics else "Standard",
        
        photos=",".join(photo_paths),
        signature=sig_path,
        status=models.MMGStatus.SENT
    )
    
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    
    return db_item

@router.get("/", response_model=List[schemas.MMGResponse])
def list_dossiers(db: Session = Depends(get_db)):
    return db.query(models.MMG).order_by(models.MMG.created_at.desc()).all()

@router.get("/{dossier_id}", response_model=schemas.MMGDetail)
def get_dossier(dossier_id: int, db: Session = Depends(get_db)):
    db_item = db.query(models.MMG).filter(models.MMG.id == dossier_id).first()
    if not db_item:
        raise HTTPException(404, "Dossier not found")
    
    return schemas.MMGDetail(
        id=db_item.id,
        reference=db_item.reference,
        client_name=db_item.client_name,
        status=db_item.status.value if hasattr(db_item.status, 'value') else db_item.status,
        created_at=db_item.created_at,
        client_contact=db_item.client_contact,
        client_address=db_item.client_address,
        site_address=db_item.site_address,
        client_email=db_item.client_email,
        client_type=db_item.client_type,
        width=db_item.width,
        height=db_item.height,
        passage_height=db_item.passage_height,
        sill_height=db_item.sill_height,
        transom_height=db_item.transom_height,
        shutter_type=db_item.shutter_type,
        opening_type=db_item.opening_type,
        opening_side=db_item.opening_side,
        sash_count=db_item.sash_count,
        view_type=db_item.view_type,
        material=db_item.material,
        product_series=db_item.product_series,
        color_ral=db_item.color_ral,
        is_bicolor=db_item.is_bicolor,
        texture=db_item.texture,
        glazing_type=db_item.glazing_type,
        installation_type=db_item.installation_type,
        hardware_type=db_item.hardware_type,
        is_pmr_compliant=db_item.is_pmr_compliant,
        doublage_thickness=db_item.doublage_thickness,
        keep_existing_frame=db_item.keep_existing_frame,
        floor_number=db_item.floor_number or 0,
        access_difficulty=db_item.access_difficulty,
        environment=db_item.environment,
        quote_sent_at=db_item.quote_sent_at,
        photos=db_item.photos.split(",") if db_item.photos else [],
        signature=db_item.signature,
        order_id=db_item.order_id
    )

@router.patch("/{dossier_id}/status", response_model=schemas.MMGResponse)
def update_status(dossier_id: int, update: schemas.MMGStatusUpdate, db: Session = Depends(get_db)):
    db_item = db.query(models.MMG).filter(models.MMG.id == dossier_id).first()
    if not db_item:
        raise HTTPException(404, "Dossier not found")
    
    previous_status = db_item.status
    db_item.status = update.status
    
    # Trigger Proges Export if validated
    if update.status == models.MMGStatus.VALIDATED and previous_status != models.MMGStatus.VALIDATED:
        from ..services import mmg_to_proges
        mmg_to_proges.save_proges_export({
            "reference": db_item.reference,
            "width": db_item.width,
            "height": db_item.height,
            "opening_type": db_item.opening_type,
            "sash_count": db_item.sash_count,
            "material": db_item.material,
            "color_ral": db_item.color_ral,
            "glazing_type": db_item.glazing_type,
            "installation_type": db_item.installation_type,
            "client_type": db_item.client_type
        })
        
    db.commit()
    db.refresh(db_item)
    return db_item

@router.post("/{dossier_id}/send-quote")
def send_quote(dossier_id: int, db: Session = Depends(get_db)):
    db_item = db.query(models.MMG).filter(models.MMG.id == dossier_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="MMG Dossier not found")
    
    db_item.quote_sent_at = datetime.utcnow()
    db.commit()
    
    # In a real app, this would generate a PDF and email it
    return {"message": "Devis généré et envoyé au client.", "sent_at": db_item.quote_sent_at}

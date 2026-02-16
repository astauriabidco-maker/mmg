from fastapi import APIRouter, Depends, HTTPException, Body, UploadFile, File
from typing import List
import shutil
import os
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, schemas
from datetime import datetime

router = APIRouter(prefix="/v2/ingest", tags=["ingest"])

@router.post("/order", response_model=schemas.Order)
def ingest_order(
    item: schemas.OrderCreate, 
    db: Session = Depends(get_db)
):
    # 1. Check if order exists (by reference)
    existing = db.query(models.Order).filter(models.Order.reference == item.reference).first()
    if existing:
        return existing # Return existing if already there (Idempotent)

    # 2. Add Order to DB
    new_order = models.Order(
        reference=item.reference,
        width=item.width,
        height=item.height,
        client_name=item.client_name,
        color=item.color,
        quantity=item.quantity,
        system_type=item.system_type,
        # Ensure Enum
        material=models.MaterialType(item.material) if isinstance(item.material, str) else item.material
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    # 3. Add to Planning (First Station from DB)
    first_station_obj = db.query(models.Station).filter(
        models.Station.material == new_order.material
    ).order_by(models.Station.order_index.asc()).first()
    
    if not first_station_obj:
        # Fallback if no stations defined in DB
        logger_station = "PVC_DEBIT" if new_order.material == models.MaterialType.PVC else "ALU_DEBIT"
    else:
        logger_station = first_station_obj.code
        
    planning = models.Planning(
        order_id=new_order.id,
        station=logger_station,
        priority=1,
        status=models.PlanningStatus.PENDING
    )
    db.add(planning)
    db.commit()

    # 4. Notify Operators (Real-time Broadcast)
    from ..core.websocket import manager
    import asyncio
    asyncio.run(manager.broadcast("refresh"))

    return new_order

@router.post("/upload")
async def upload_order_file(file: UploadFile = File(...)):
    """
    Receive a manual upload and save it to input_orders for the watcher to process.
    """
    try:
        INPUT_DIR = "input_orders"
        if not os.path.exists(INPUT_DIR):
            os.makedirs(INPUT_DIR)
            
        file_path = os.path.join(INPUT_DIR, file.filename)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        return {"filename": file.filename, "status": "deposited", "message": "File will be processed by OCR shortly."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@router.get("/recent", response_model=List[schemas.Order])
def get_recent_orders(db: Session = Depends(get_db)):
    return db.query(models.Order).order_by(models.Order.id.desc()).limit(10).all()

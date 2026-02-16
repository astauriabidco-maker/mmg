from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from .. import models, schemas

router = APIRouter(prefix="/v2/planning", tags=["planning"])

@router.get("/{station}", response_model=List[schemas.Planning])
def get_queue(station: str, db: Session = Depends(get_db)):
    # Get pending or in_progress items for this station, ordered by priority
    queue = db.query(models.Planning).filter(
        models.Planning.station == station,
        models.Planning.status.in_([
            models.PlanningStatus.PENDING, 
            models.PlanningStatus.IN_PROGRESS,
            models.PlanningStatus.PAUSED,
            models.PlanningStatus.ISSUE
        ])
    ).order_by(models.Planning.priority.desc(), models.Planning.created_at).all()
    return queue

@router.post("/", response_model=schemas.Planning)
def add_to_planning(item: schemas.PlanningCreate, db: Session = Depends(get_db)):
    # Find order
    order = db.query(models.Order).filter(models.Order.reference == item.order_reference).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    new_plan = models.Planning(
        order_id=order.id,
        station=item.station,
        priority=item.priority,
        status=models.PlanningStatus.PENDING
    )
    db.add(new_plan)
    db.commit()
    db.refresh(new_plan)
    return new_plan

@router.post("/{planning_id}/start")
async def start_task(planning_id: int, db: Session = Depends(get_db)):
    from ..core.websocket import manager
    from datetime import datetime
    
    task = db.query(models.Planning).filter(models.Planning.id == planning_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
        
    task.status = models.PlanningStatus.IN_PROGRESS
    
    # Create Production Log (V1 compatibility logic)
    log = models.ProductionLog(
        order_id=task.order_id,
        station=task.station,
        material="Unknown", # Should fetch from order
        start_time=datetime.utcnow()
    )
    # Fetch material from order
    order = db.query(models.Order).filter(models.Order.id == task.order_id).first()
    if order:
        log.material = order.material.value if hasattr(order.material, 'value') else order.material

    db.add(log)
    db.commit()
    
    await manager.broadcast("refresh")
    return {"status": "started"}

# Logic replaced by DB-driven workflow in stop_task

@router.post("/{planning_id}/pause")
async def pause_task(planning_id: int, db: Session = Depends(get_db)):
    from ..core.websocket import manager
    from datetime import datetime
    
    task = db.query(models.Planning).filter(models.Planning.id == planning_id).first()
    if not task:
        raise HTTPException(404, "Task not found")

    if task.status != models.PlanningStatus.IN_PROGRESS:
        raise HTTPException(400, "Task is not in progress")
        
    task.status = models.PlanningStatus.PAUSED
    
    # Close current log segment
    log = db.query(models.ProductionLog).filter(
        models.ProductionLog.order_id == task.order_id,
        models.ProductionLog.station == task.station,
        models.ProductionLog.end_time.is_(None)
    ).first()
    
    if log:
        log.end_time = datetime.utcnow()
        log.duration_seconds = (log.end_time - log.start_time).seconds

    db.commit()
    await manager.broadcast("refresh")
    return {"status": "paused"}

@router.post("/{planning_id}/stop")
async def stop_task(planning_id: int, db: Session = Depends(get_db)):
    from ..core.websocket import manager
    from datetime import datetime
    
    task = db.query(models.Planning).filter(models.Planning.id == planning_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
        
    task.status = models.PlanningStatus.DONE
    
    # Close Production Log
    log = db.query(models.ProductionLog).filter(
        models.ProductionLog.order_id == task.order_id,
        models.ProductionLog.station == task.station,
        models.ProductionLog.end_time.is_(None)
    ).first()
    
    if log:
        log.end_time = datetime.utcnow()
        log.duration_seconds = (log.end_time - log.start_time).seconds
    
    # --- AUTO-WORKFLOW LOGIC (Dynamic from DB) ---
    order = db.query(models.Order).filter(models.Order.id == task.order_id).first()
    next_station = None
    
    if order:
        # 1. Get current station details
        current_station_obj = db.query(models.Station).filter(
            models.Station.code == task.station
        ).first()
        
        if current_station_obj:
            # 2. Find next station for same material with higher order_index
            next_station_obj = db.query(models.Station).filter(
                models.Station.material == order.material,
                models.Station.order_index > current_station_obj.order_index
            ).order_by(models.Station.order_index.asc()).first()
            
            if next_station_obj:
                next_station = next_station_obj.code
            
    if next_station:
        # Check if already exists to avoid dupes
        exists = db.query(models.Planning).filter(
            models.Planning.order_id == task.order_id,
            models.Planning.station == next_station
        ).first()
        
        if not exists:
            new_plan = models.Planning(
                order_id=task.order_id,
                station=next_station,
                priority=task.priority,
                status=models.PlanningStatus.PENDING
            )
            db.add(new_plan)
    # ---------------------------

    db.commit()
    
    await manager.broadcast("refresh")
    return {"status": "stopped", "next_station": next_station}

@router.post("/{planning_id}/issue")
async def report_issue(planning_id: int, item: schemas.PlanningIssue, db: Session = Depends(get_db)):
    from ..core.websocket import manager
    from datetime import datetime
    
    task = db.query(models.Planning).filter(models.Planning.id == planning_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
        
    task.status = models.PlanningStatus.ISSUE
    task.issue_notes = item.notes
    
    # Close Production Log if running
    log = db.query(models.ProductionLog).filter(
        models.ProductionLog.order_id == task.order_id,
        models.ProductionLog.station == task.station,
        models.ProductionLog.end_time.is_(None)
    ).first()
    
    if log:
        log.end_time = datetime.utcnow()
        log.duration_seconds = (log.end_time - log.start_time).seconds
    
    db.commit()
    await manager.broadcast("refresh")
    
    print(f"!!! PROBLEM REPORTED ON ORDER {task.order_id} STATION {task.station}: {item.notes} !!!")
    
    return {"status": "issue_reported"}

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from pydantic import BaseModel
from datetime import datetime, timezone
from ..database import get_db
from .. import models, schemas
from ..core.security import get_current_user, require_permissions, assert_permission

router = APIRouter(prefix="/v2/planning", tags=["planning"])

def _task_to_overview(task: models.Planning) -> Dict[str, Any]:
    order = task.order
    created_at = task.created_at
    now = datetime.now(timezone.utc)
    if created_at and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_hours = round((now - created_at).total_seconds() / 3600, 1) if created_at else 0
    is_late = task.status in [models.PlanningStatus.PENDING, models.PlanningStatus.PAUSED, models.PlanningStatus.ISSUE] and age_hours >= 24
    return {
        "id": task.id,
        "station": task.station,
        "status": task.status.value if hasattr(task.status, "value") else task.status,
        "priority": task.priority or 0,
        "assigned_to": task.assigned_to,
        "issue_notes": task.issue_notes,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "age_hours": age_hours,
        "is_late": is_late,
        "order_id": task.order_id,
        "order_reference": task.order_reference,
        "client_name": order.client_name if order else None,
        "material": order.material.value if order and hasattr(order.material, "value") else (order.material if order else None),
        "quantity": order.quantity if order else None,
        "sale_order_id": order.sale_order_id if order else None,
    }

@router.get("/overview")
def get_workshop_overview(db: Session = Depends(get_db), current_user: dict = Depends(require_permissions("PROD_VIEW"))):
    active_statuses = [
        models.PlanningStatus.PENDING,
        models.PlanningStatus.IN_PROGRESS,
        models.PlanningStatus.PAUSED,
        models.PlanningStatus.ISSUE,
    ]
    stations = db.query(models.Station).order_by(models.Station.material.asc(), models.Station.order_index.asc()).all()
    tasks = (
        db.query(models.Planning)
        .filter(models.Planning.status.in_(active_statuses))
        .order_by(models.Planning.priority.desc(), models.Planning.created_at.asc())
        .all()
    )
    station_map = {
        station.code: {
            "code": station.code,
            "display_name": station.display_name,
            "material": station.material.value if hasattr(station.material, "value") else station.material,
            "order_index": station.order_index,
            "queue": 0,
            "in_progress": 0,
            "paused": 0,
            "issues": 0,
            "late": 0,
            "load_score": 0,
            "tasks": [],
        }
        for station in stations
    }
    unassigned_station = {
        "code": "UNCONFIGURED",
        "display_name": "Stations non configurées",
        "material": "MIXTE",
        "order_index": 999,
        "queue": 0,
        "in_progress": 0,
        "paused": 0,
        "issues": 0,
        "late": 0,
        "load_score": 0,
        "tasks": [],
    }

    for task in tasks:
        payload = _task_to_overview(task)
        station = station_map.get(task.station)
        if station is None:
            station = unassigned_station
        station["tasks"].append(payload)
        if task.status == models.PlanningStatus.PENDING:
            station["queue"] += 1
        elif task.status == models.PlanningStatus.IN_PROGRESS:
            station["in_progress"] += 1
        elif task.status == models.PlanningStatus.PAUSED:
            station["paused"] += 1
        elif task.status == models.PlanningStatus.ISSUE:
            station["issues"] += 1
        if payload["is_late"]:
            station["late"] += 1

    stations_payload = list(station_map.values())
    if unassigned_station["tasks"]:
        stations_payload.append(unassigned_station)

    for station in stations_payload:
        station["load_score"] = station["queue"] + station["in_progress"] * 2 + station["paused"] * 2 + station["issues"] * 4 + station["late"] * 3
        station["tasks"].sort(key=lambda item: (item["status"] != "ISSUE", -item["priority"], item["created_at"] or ""))

    blocked_tasks = [task for station in stations_payload for task in station["tasks"] if task["status"] == "ISSUE"]
    late_tasks = [task for station in stations_payload for task in station["tasks"] if task["is_late"]]
    priority_tasks = sorted(
        [task for station in stations_payload for task in station["tasks"]],
        key=lambda item: (item["status"] != "ISSUE", not item["is_late"], -item["priority"], item["created_at"] or ""),
    )[:12]

    return {
        "summary": {
            "stations": len(stations_payload),
            "active_tasks": len(tasks),
            "in_progress": sum(station["in_progress"] for station in stations_payload),
            "queue": sum(station["queue"] for station in stations_payload),
            "paused": sum(station["paused"] for station in stations_payload),
            "blocked": len(blocked_tasks),
            "late": len(late_tasks),
        },
        "stations": stations_payload,
        "blocked_tasks": blocked_tasks,
        "late_tasks": late_tasks,
        "priority_tasks": priority_tasks,
    }

@router.get("/{station}", response_model=List[schemas.Planning])
def get_queue(station: str, db: Session = Depends(get_db), current_user: dict = Depends(require_permissions("PROD_VIEW"))):
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

class CuttingRequest(BaseModel):
    pieces: List[float] # List of required lengths in mm
    bar_length: float = 6000.0 # Standard bar length in mm

@router.post("/optimize-cutting")
def optimize_cutting_plan(req: CuttingRequest, db: Session = Depends(get_db), current_user: dict = Depends(require_permissions("PROD_EDIT"))):
    """
    Simulated "Directeur de Production IA".
    Uses a greedy approach (First Fit Decreasing) for 1D Bin Packing to optimize cuts.
    Now dynamically connected to the BusinessRules database!
    """
    bar_length_rule = db.query(models.BusinessRule).filter(models.BusinessRule.rule_key == 'longueur_barre_alu').first()
    blade_thickness_rule = db.query(models.BusinessRule).filter(models.BusinessRule.rule_key == 'epaisseur_lame').first()
    alert_threshold_rule = db.query(models.BusinessRule).filter(models.BusinessRule.rule_key == 'seuil_chute').first()
    
    actual_bar_length = float(bar_length_rule.value) if bar_length_rule else req.bar_length
    blade_thickness = float(blade_thickness_rule.value) if blade_thickness_rule else 4.0
    alert_threshold = float(alert_threshold_rule.value) if alert_threshold_rule else 15.0

    # Adjust piece sizes by adding blade thickness to account for cut loss
    adjusted_pieces = [p + blade_thickness for p in req.pieces]
    pieces = sorted(adjusted_pieces, reverse=True)
    bars = [] # List of bars, where each bar is a list of pieces
    
    for piece in pieces:
        if piece > actual_bar_length:
            raise HTTPException(400, f"Piece (avec lame) {piece}mm est plus longue que la barre de {actual_bar_length}mm")
            
        placed = False
        for bar in bars:
            if sum(bar) + piece <= actual_bar_length:
                bar.append(piece)
                placed = True
                break
                
        if not placed:
            bars.append([piece])
            
    # Calculate stats
    total_material_used = len(bars) * actual_bar_length
    total_pieces_length = sum(pieces)
    waste_percentage = ((total_material_used - total_pieces_length) / total_material_used) * 100 if total_material_used > 0 else 0
    
    formatted_bars = []
    for idx, bar in enumerate(bars):
        used = sum(bar)
        waste = actual_bar_length - used
        # Revert blade thickness for display purposes so user sees their requested length
        original_cuts = [c - blade_thickness for c in bar]
        formatted_bars.append({
            "bar_id": idx + 1,
            "cuts": original_cuts,
            "used": used,
            "waste": waste,
            "utilization": (used / actual_bar_length) * 100
        })
        
    ai_status = "⚠️ ATTENTION" if waste_percentage > alert_threshold else "✅ OPTIMUM"
    
    return {
        "total_bars_required": len(bars),
        "total_waste_percentage": round(waste_percentage, 2),
        "bars": formatted_bars,
        "ai_message": f"🧠 Optimisation dynamique : Lame ({blade_thickness}mm). {len(bars)} barres ({actual_bar_length}mm) requises. Chute : {round(waste_percentage, 2)}% ({ai_status})."
    }

@router.post("/", response_model=schemas.Planning)
def add_to_planning(item: schemas.PlanningCreate, db: Session = Depends(get_db), current_user: dict = Depends(require_permissions("planning:assign"))):
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

class PlanningUpdateRequest(BaseModel):
    priority: int = None
    assigned_to: str = None
    status: str = None

@router.put("/{planning_id}")
async def update_planning(planning_id: int, req: PlanningUpdateRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    from ..core.websocket import manager
    task = db.query(models.Planning).filter(models.Planning.id == planning_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
        
    if req.priority is not None:
        assert_permission(db, current_user, "planning:reprioritize")
        task.priority = req.priority
    if req.assigned_to is not None:
        assert_permission(db, current_user, "planning:assign")
        task.assigned_to = req.assigned_to
    if req.status is not None:
        if req.status == models.PlanningStatus.PENDING or req.status == "PENDING":
            assert_permission(db, current_user, "planning:unblock")
        else:
            assert_permission(db, current_user, "planning:reprioritize")
        task.status = req.status
        
    db.commit()
    await manager.broadcast("refresh")
    return {"status": "updated"}

@router.post("/{planning_id}/start")
async def start_task(planning_id: int, db: Session = Depends(get_db), current_user: dict = Depends(require_permissions("planning:start"))):
    from ..core.websocket import manager
    from datetime import datetime
    
    task = db.query(models.Planning).filter(models.Planning.id == planning_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
        
    task.status = models.PlanningStatus.IN_PROGRESS
    operator_name = current_user.get("sub", "Operator")
    task.assigned_to = operator_name
    
    # Create Production Log
    log = models.ProductionLog(
        order_id=task.order_id,
        station=task.station,
        material="Unknown", # Should fetch from order
        operator_name=operator_name,
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
async def pause_task(planning_id: int, db: Session = Depends(get_db), current_user: dict = Depends(require_permissions("planning:pause"))):
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
async def stop_task(planning_id: int, db: Session = Depends(get_db), current_user: dict = Depends(require_permissions("planning:stop"))):
    from ..core.websocket import manager
    from datetime import datetime
    
    task = db.query(models.Planning).filter(models.Planning.id == planning_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if "DEBIT" in str(task.station or "").upper():
        assert_permission(db, current_user, "planning:consume_stock")
        
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
    else:
        # Production is finished, generate DeliveryNote
        # Check if one already exists
        exists_note = db.query(models.DeliveryNote).filter(models.DeliveryNote.order_id == task.order_id).first()
        if not exists_note and order:
            from datetime import datetime
            year = datetime.utcnow().year
            count = db.query(models.DeliveryNote).filter(models.DeliveryNote.reference.like(f"BL-{year}-%")).count()
            ref = f"BL-{year}-{count + 1:04d}"
            
            note = models.DeliveryNote(
                reference=ref,
                order_id=task.order_id,
                client_name=order.client_name,
                delivery_address="", # Will be filled by dispatcher or from sale order
                status="READY"
            )
            db.add(note)
    # ---------------------------

    # --- STOCK AUTO-DEDUCTION ---
    from ..services.stock_service import StockService
    try:
        stock_result = StockService.deduct_stock_for_order(
            db,
            task.order_id,
            task.station,
            author=current_user.get("sub", "Atelier"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    db.commit()
    
    await manager.broadcast("refresh")
    return {"status": "stopped", "next_station": next_station, "stock": stock_result}

@router.post("/{planning_id}/issue")
async def report_issue(planning_id: int, item: schemas.PlanningIssue, db: Session = Depends(get_db), current_user: dict = Depends(require_permissions("planning:report_issue"))):
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

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict
from datetime import datetime, date, timedelta
from ..database import get_db
from .. import models
from ..core.config import STANDARDS, ALERT_THRESHOLD_PERCENT

router = APIRouter(prefix="/v2/analytics", tags=["analytics"])

@router.get("/daily")
def get_daily_stats(db: Session = Depends(get_db)):
    today = datetime.utcnow().date()
    # In SQLite, date comparison might need slight adjustment depending on storage format.
    # We stored DateTime. Let's filter >= today midnight.
    start_of_day = datetime(today.year, today.month, today.day)
    
    # Query logs
    logs = db.query(models.ProductionLog).filter(models.ProductionLog.start_time >= start_of_day).all()
    
    total = len(logs)
    avg_time = 0
    if total > 0:
        completed = [l for l in logs if l.end_time]
        if completed:
            durations = [(c.end_time - c.start_time).total_seconds() for c in completed]
            avg_time = int(sum(durations) / len(durations))

    delayed_count = 0
    for l in logs:
        # Determine standard
        # Standard stored in config is by Station (e.g. "PVC_DEBIT": 35)
        # Log has station enum.
        station_val = l.station if l.station else "UNKNOWN"
        std_min = STANDARDS.get(station_val, 30) # Default 30 if unknown
        std_sec = std_min * 60
        threshold = std_sec * (ALERT_THRESHOLD_PERCENT / 100)
        
        if l.duration_seconds and l.duration_seconds > threshold:
            delayed_count += 1
            
    delay_rate = 0
    if total > 0:
        delay_rate = int((delayed_count / total) * 100)
    
    # Active orders (not completed)
    active = db.query(models.ProductionLog).filter(
        models.ProductionLog.start_time >= start_of_day,
        models.ProductionLog.end_time.is_(None)
    ).count()

    return {
        "total": total,
        "avg_time": f"{avg_time // 60}m {avg_time % 60}s",
        "delay_rate": delay_rate,
        "active": active
    }

@router.get("/hourly")
def get_hourly_stats(db: Session = Depends(get_db)):
    # Simple hourly aggregation
    # SQLite strftime('%H', start_time)
    today = datetime.utcnow().date()
    start_of_day = datetime(today.year, today.month, today.day)
    
    results = db.query(
        func.strftime('%H', models.ProductionLog.start_time).label('hour'),
        func.count(models.ProductionLog.id).label('count')
    ).filter(
        models.ProductionLog.start_time >= start_of_day
    ).group_by('hour').all()
    
    # Format for Recharts [{name: '08:00', count: 5}, ...]
    data = []
    hours_map = {int(r.hour): r.count for r in results}
    
    for h in range(8, 19): # 8h to 18h
        data.append({
            "name": f"{h}:00",
            "count": hours_map.get(h, 0)
        })
        
    return data

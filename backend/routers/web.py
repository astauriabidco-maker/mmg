from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from .. import database
from ..services.production import ProductionService
from ..services.kpi import KpiService

router = APIRouter()
templates = Jinja2Templates(directory="backend/templates")

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    logs = KpiService.get_daily_logs(db)
    display_logs, alerts = KpiService.process_logs(logs)
    
    # KPI Logic (Lightweight)
    orders = set(l["order_ref"] for l in display_logs)
    active = sum(1 for l in display_logs if not l["end_time"])
    completed = [l["real_min"] for l in display_logs if l["end_time"]]
    avg = round(sum(completed) / len(completed), 1) if completed else 0
    
    kpi = {
        "total_orders": len(orders),
        "active_orders": active,
        "avg_time_day": avg,
        "alerts_count": len(alerts)
    }

    return templates.TemplateResponse("index.html", {
        "request": request, "logs": display_logs, "kpi": kpi, 
        "now": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "page": "dashboard"
    })

@router.get("/alertes", response_class=HTMLResponse)
def alertes(request: Request, db: Session = Depends(get_db)):
    logs = KpiService.get_daily_logs(db)
    _, alerts = KpiService.process_logs(logs)
    alerts.sort(key=lambda x: x["percent"], reverse=True)
    return templates.TemplateResponse("alertes.html", {
        "request": request, "alerts": alerts,
        "now": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "page": "alertes"
    })

@router.get("/export/csv")
def export_csv(db: Session = Depends(get_db)):
    csv_content = KpiService.generate_csv_export(db)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=production_{datetime.now().strftime('%Y%m%d')}.csv"}
    )

@router.post("/start")
def start(
    order_reference: str = Form(...),
    station: str = Form(...),
    material: str = Form(...),
    db: Session = Depends(get_db)
):
    ProductionService.start_production(db, order_reference, station, material)
    return RedirectResponse(url="/", status_code=303)

@router.post("/stop")
def stop(
    order_reference: str = Form(...),
    station: str = Form(...),
    db: Session = Depends(get_db)
):
    ProductionService.stop_production(db, order_reference, station)
    return RedirectResponse(url="/", status_code=303)

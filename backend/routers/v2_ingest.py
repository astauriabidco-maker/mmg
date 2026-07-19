from fastapi import APIRouter, Depends, HTTPException, Body, UploadFile, File, Response
from typing import List
import shutil
import os
import csv
from io import BytesIO, StringIO
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, schemas
from ..core import security
from ..core import uploads
from datetime import datetime

router = APIRouter(
    prefix="/v2/ingest",
    tags=["ingest"],
    dependencies=[Depends(security.get_current_user)],
)


@router.post("/order", response_model=schemas.Order)
def ingest_order(
    item: schemas.OrderCreate, 
    db: Session = Depends(get_db),
    role: str = Depends(security.require_roles("ADMIN", "MANAGER"))
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
async def upload_order_file(file: UploadFile = File(...), role: str = Depends(security.require_roles("ADMIN", "MANAGER"))):
    """
    Receive a manual upload and save it to input_orders for the watcher to process.
    Les débits atelier TXT sont acceptés sur cet endpoint uniquement.
    """
    INPUT_DIR = "input_orders"
    file_path = await uploads.save_upload_file(file, INPUT_DIR, extra_extensions={".txt"})
    return {"filename": os.path.basename(file_path), "status": "deposited", "message": "File will be processed by OCR shortly."}
@router.get("/recent", response_model=List[schemas.Order])
def get_recent_orders(db: Session = Depends(get_db)):
    return db.query(models.Order).order_by(models.Order.id.desc()).limit(10).all()

@router.get("/orders/tracking")
def get_orders_tracking(db: Session = Depends(get_db)):
    """Suivi enrichi de toutes les commandes de fabrication avec statut dynamique."""
    orders = db.query(models.Order).order_by(models.Order.id.desc()).all()
    result = []
    
    for order in orders:
        # Get all planning entries for this order
        plans = db.query(models.Planning).filter(models.Planning.order_id == order.id).order_by(models.Planning.created_at.asc()).all()
        
        # Compute overall status
        if not plans:
            status = "NEW"
            current_station = None
            progress = 0
        else:
            statuses = [p.status.value if hasattr(p.status, 'value') else str(p.status) for p in plans]
            done_count = statuses.count("DONE")
            total_count = len(statuses)
            progress = int((done_count / total_count) * 100) if total_count > 0 else 0
            
            # Find current active task
            active = next((p for p in plans if p.status in [models.PlanningStatus.IN_PROGRESS]), None)
            paused = next((p for p in plans if p.status in [models.PlanningStatus.PAUSED]), None)
            issue = next((p for p in plans if p.status in [models.PlanningStatus.ISSUE]), None)
            pending = next((p for p in plans if p.status in [models.PlanningStatus.PENDING]), None)
            
            if issue:
                status = "ISSUE"
                current_station = issue.station
            elif active:
                status = "IN_PROGRESS"
                current_station = active.station
            elif paused:
                status = "PAUSED"
                current_station = paused.station
            elif pending:
                status = "PENDING"
                current_station = pending.station
            elif done_count == total_count:
                # Check if delivery note exists
                has_bl = db.query(models.DeliveryNote).filter(models.DeliveryNote.order_id == order.id).first()
                status = "DELIVERED" if (has_bl and has_bl.status == "DELIVERED") else "READY"
                current_station = None
            else:
                status = "PENDING"
                current_station = plans[-1].station if plans else None
        
        # Get station display name
        station_display = None
        if current_station:
            station_obj = db.query(models.Station).filter(models.Station.code == current_station).first()
            station_display = station_obj.display_name if station_obj else current_station.replace("_", " ")
        
        # Get assigned operator
        assigned = next((p.assigned_to for p in plans if p.assigned_to), None)
        
        result.append({
            "id": order.id,
            "reference": order.reference,
            "client_name": order.client_name,
            "width": order.width,
            "height": order.height,
            "material": order.material.value if hasattr(order.material, 'value') else str(order.material),
            "quantity": order.quantity,
            "color": order.color,
            "system_type": order.system_type,
            "status": status,
            "progress": progress,
            "current_station": current_station,
            "station_display": station_display,
            "assigned_to": assigned,
            "steps": [{"station": p.station, "status": p.status.value if hasattr(p.status, 'value') else str(p.status)} for p in plans]
        })
    
    return result


def _get_tracking_data(db: Session):
    """Helper: reuse tracking logic for exports."""
    # Call the tracking endpoint logic internally
    return get_orders_tracking(db)

STATUS_LABELS = {
    "NEW": "Nouveau", "PENDING": "En attente", "IN_PROGRESS": "En cours",
    "PAUSED": "En pause", "DONE": "Terminé", "READY": "Prêt à livrer",
    "DELIVERED": "Livré", "ISSUE": "Incident", "DEFECT": "Défaut"
}

@router.get("/orders/export/csv")
def export_orders_csv(db: Session = Depends(get_db)):
    """Export du carnet de commandes en CSV (Excel-friendly)."""
    data = _get_tracking_data(db)
    
    output = StringIO()
    # BOM for Excel UTF-8 compatibility
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';')
    
    # Header
    writer.writerow(["Référence", "Client", "Matériau", "Dimensions (mm)", "Quantité", "Couleur", "Système", "Statut", "Progression (%)", "Station actuelle", "Opérateur"])
    
    for o in data:
        writer.writerow([
            o["reference"],
            o["client_name"] or "",
            o["material"],
            f'{o["width"]} x {o["height"]}',
            o["quantity"],
            o["color"] or "",
            o["system_type"] or "",
            STATUS_LABELS.get(o["status"], o["status"]),
            f'{o["progress"]}%',
            o["station_display"] or "",
            o["assigned_to"] or ""
        ])
    
    csv_content = output.getvalue()
    output.close()
    
    filename = f"Carnet_Commandes_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/orders/export/pdf")
def export_orders_pdf(db: Session = Depends(get_db)):
    """Export PDF professionnel du carnet de commandes."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    data = _get_tracking_data(db)
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(name='TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor("#1e293b"), spaceAfter=10)
    small_style = ParagraphStyle(name='SmallStyle', parent=styles['Normal'], fontSize=7, leading=9)
    
    # Header
    elements.append(Paragraph("MMG MENUISERIES — Carnet de Commandes", title_style))
    elements.append(Paragraph(f"Généré le {datetime.utcnow().strftime('%d/%m/%Y à %H:%M')} — {len(data)} commande(s)", styles['Normal']))
    elements.append(Spacer(1, 15))
    
    # Table
    table_data = [["Réf.", "Client", "Mat.", "Dimensions", "Qté", "Statut", "Progression", "Station", "Opérateur"]]
    
    for o in data:
        table_data.append([
            Paragraph(o["reference"], small_style),
            Paragraph(o["client_name"] or "—", small_style),
            o["material"],
            f'{o["width"]}x{o["height"]}',
            str(o["quantity"]),
            STATUS_LABELS.get(o["status"], o["status"]),
            f'{o["progress"]}%',
            Paragraph(o["station_display"] or "—", small_style),
            Paragraph(o["assigned_to"] or "—", small_style),
        ])
    
    col_widths = [75, 110, 35, 70, 30, 75, 55, 100, 80]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor("#334155")),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(t)
    
    # Footer
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(f"Document généré automatiquement par MMG ERP — {len(data)} commande(s) au total.", styles['Normal']))
    
    doc.build(elements)
    pdf_value = buffer.getvalue()
    buffer.close()
    
    filename = f"Carnet_Commandes_{datetime.utcnow().strftime('%Y%m%d')}.pdf"
    return Response(
        content=pdf_value,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

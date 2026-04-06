from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List

from ..database import get_db
from .. import models, schemas
from ..core.security import get_current_user

import io

router = APIRouter(
    prefix="/v2/sales",
    tags=["sales_v2"],
    responses={404: {"description": "Non trouvé"}}
)

@router.get("/", response_model=List[schemas.SaleOrderSchema])
def list_sales(db: Session = Depends(get_db)):
    return db.query(models.SaleOrder).order_by(models.SaleOrder.created_at.desc()).all()

@router.post("/", response_model=schemas.SaleOrderSchema)
def create_sale_order(order_req: schemas.SaleOrderCreate, db: Session = Depends(get_db)):
    date_str = datetime.now().strftime("%Y-%m-%d-%H%M")
    ref = f"DEV-{date_str}"
    
    order = models.SaleOrder(
        reference=ref,
        client_name=order_req.client_name,
        client_contact=order_req.client_contact,
        client_email=order_req.client_email,
        client_address=order_req.client_address,
        validity_days=order_req.validity_days,
        tax_rate=order_req.tax_rate,
        currency=order_req.currency,
        notes=order_req.notes,
        status="DRAFT",
        author="Admin" # TODO link with user
    )
    db.add(order)
    db.flush()
    
    for l in order_req.lines:
        line = models.SaleOrderLine(
            order_id=order.id,
            variant_id=l.variant_id,
            description=l.description,
            quantity=l.quantity,
            unit_price=l.unit_price,
            discount_pct=l.discount_pct
        )
        db.add(line)
        
    db.commit()
    db.refresh(order)
    return order

@router.get("/{order_id}", response_model=schemas.SaleOrderSchema)
def get_sale_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(models.SaleOrder).filter(models.SaleOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Devis introuvable.")
    return order

@router.put("/{order_id}/status")
def update_sale_status(order_id: int, status: str, db: Session = Depends(get_db)):
    order = db.query(models.SaleOrder).filter(models.SaleOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Devis introuvable.")
        
    order.status = status
    db.commit()
    return {"message": f"Statut mis à jour : {status}"}

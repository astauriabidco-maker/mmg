from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List

from ..database import get_db
from .. import models, schemas
from ..core.security import get_current_user

router = APIRouter(
    prefix="/v2/pos",
    tags=["pos_v2"],
    responses={404: {"description": "Non trouvé"}}
)

@router.get("/sessions/active", response_model=schemas.POSSessionSchema)
def get_active_session(db: Session = Depends(get_db)):
    session = db.query(models.POSSession).filter(models.POSSession.status == "OPEN").order_by(models.POSSession.id.desc()).first()
    if not session:
        raise HTTPException(status_code=404, detail="Aucune caisse ouverte.")
    return session

@router.get("/items")
def get_pos_items(db: Session = Depends(get_db)):
    variants = db.query(models.ProductVariant).join(models.ProductVariant.product).filter(
        models.Product.available_in_pos == True
    ).all()
    
    results = []
    for v in variants:
        results.append({
            "variant_id": v.id,
            "product_name": f"{v.product.name} ({v.color or 'Std'})",
            "reference": v.reference,
            "barcode": v.barcode,
            "price": v.cost_price or 0, # Note: using cost_price as sell_price for mockup
            "stock": v.quantity_in_stock
        })
    return results

@router.post("/sessions/open", response_model=schemas.POSSessionSchema)
def open_session(starting_cash: float = 0.0, db: Session = Depends(get_db)):
    active = db.query(models.POSSession).filter(models.POSSession.status == "OPEN").first()
    if active:
        raise HTTPException(status_code=400, detail="Une session est déjà ouverte.")
        
    date_str = datetime.now().strftime("%Y%m%d%H%M")
    ref = f"POS-S-{date_str}"
    
    new_session = models.POSSession(
        reference=ref,
        opened_by_user="Admin", # TODO connect to current_user
        starting_cash=starting_cash,
        status="OPEN"
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return new_session

@router.post("/sessions/{session_id}/close")
def close_session(session_id: int, closing_cash: float, db: Session = Depends(get_db)):
    session = db.query(models.POSSession).filter(models.POSSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvée.")
    if session.status == "CLOSED":
        raise HTTPException(status_code=400, detail="Session déjà fermée.")
        
    session.status = "CLOSED"
    session.closed_at = datetime.utcnow()
    session.closing_cash = closing_cash
    db.commit()
    return {"message": "Caisse fermée avec succès", "expected": session.starting_cash, "actual": closing_cash}

@router.post("/checkout", response_model=schemas.POSOrderSchema)
def pos_checkout(req: schemas.POSCheckoutRequest, db: Session = Depends(get_db)):
    session = db.query(models.POSSession).filter(models.POSSession.status == "OPEN").first()
    if not session:
        raise HTTPException(status_code=400, detail="Aucune session de caisse ouverte.")
        
    if not req.items:
        raise HTTPException(status_code=400, detail="Panier vide")
        
    # Calculate sum
    amount_total = sum(item.quantity * item.price for item in req.items)
    # Return 
    amount_return = max(0.0, req.amount_paid - amount_total)
    
    date_str = datetime.now().strftime("%Y%m%d%H%M%S")
    ref = f"TK-{date_str}"
    
    order = models.POSOrder(
        session_id=session.id,
        reference=ref,
        payment_method=req.payment_method,
        tax_rate=req.tax_rate,
        currency=req.currency,
        amount_total=amount_total,
        amount_paid=req.amount_paid,
        amount_return=amount_return
    )
    db.add(order)
    db.flush()
    
    global_location = db.query(models.StockLocation).filter(models.StockLocation.id == 1).first() # Default location 1
    
    for item in req.items:
        ol = models.POSOrderLine(
            order_id=order.id,
            variant_id=item.variant_id,
            product_name=item.product_name,
            quantity=item.quantity,
            unit_price=item.price
        )
        db.add(ol)
        
        # Deduct stock
        quant = db.query(models.StockQuant).filter(
            models.StockQuant.variant_id == item.variant_id,
            models.StockQuant.location_id == global_location.id
        ).first()
        
        if quant:
            quant.quantity -= item.quantity
        else:
            new_quant = models.StockQuant(
                variant_id=item.variant_id,
                location_id=global_location.id,
                quantity=-item.quantity
            )
            db.add(new_quant)
            
        # Deduct global variant fallback
        variant = db.query(models.ProductVariant).filter(models.ProductVariant.id == item.variant_id).first()
        if variant:
            variant.quantity_in_stock -= item.quantity
            
        # Log stock move
        mv = models.StockMove(
            reference=f"POS Out - {ref}",
            variant_id=item.variant_id,
            location_id=global_location.id,
            location_dest_id=8, # Virtual Customer Location if exists, 
            quantity=item.quantity,
            state="done",
            author="POS System",
            notes=f"Vente Caisse Ticket {ref}"
        )
        db.add(mv)
        
    db.commit()
    db.refresh(order)
    return order

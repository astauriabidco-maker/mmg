from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List

from ..database import get_db
from .. import models, schemas
from ..core.security import get_current_user
from ..services.stock_service import InventoryService
from .v2_accounting import generate_invoice_reference, compute_qr_seal

router = APIRouter(
    prefix="/v2/pos",
    tags=["pos_v2"],
    dependencies=[Depends(get_current_user)],
    responses={404: {"description": "Non trouvé"}}
)

@router.get("/sessions/active", response_model=schemas.POSSessionSchema)
def get_active_session(db: Session = Depends(get_db)):
    session = db.query(models.POSSession).filter(models.POSSession.status == "OPEN").order_by(models.POSSession.id.desc()).first()
    if not session:
        raise HTTPException(status_code=404, detail="Aucune caisse ouverte.")
    return session

@router.get("/invoices/pending")
def get_pending_invoices(db: Session = Depends(get_db)):
    invoices = db.query(models.Invoice).filter(models.Invoice.status.in_(["DRAFT", "UNPAID", "PARTIAL"])).all()
    results = []
    for inv in invoices:
        paid_amount = sum(p.amount for p in inv.payments)
        due_amount = inv.total - paid_amount
        if due_amount > 0:
            results.append({
                "id": inv.id,
                "reference": inv.reference,
                "client_name": inv.client_name,
                "total": inv.total,
                "due_amount": due_amount,
                "issue_date": inv.issue_date
            })
    return results

@router.post("/invoices/{invoice_id}/pay")
def pay_invoice_pos(invoice_id: int, req: schemas.POSInvoicePaymentReq, db: Session = Depends(get_db)):
    session = db.query(models.POSSession).filter(models.POSSession.status == "OPEN").first()
    if not session:
        raise HTTPException(status_code=400, detail="Caisse fermée.")
        
    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(404, "Facture non trouvée")
        
    pmt = models.Payment(
        invoice_id=invoice.id,
        amount=req.amount,
        method=req.method,
        reference=f"Payé en Caisse ({session.reference})"
    )
    db.add(pmt)
    
    if req.method == "CASH":
        mv = models.POSCashMovement(
            session_id=session.id,
            movement_type="IN",
            amount=req.amount,
            reason=f"Paiement Facture {invoice.reference}",
            author=req.author
        )
        db.add(mv)
        
    db.flush()
    paid_amount = sum(p.amount for p in invoice.payments)
    if paid_amount >= invoice.total:
        invoice.status = "PAID"
    else:
        invoice.status = "PARTIAL"
        
    db.commit()
    return {"message": "Facture encaissée avec succès"}

@router.get("/items")
def get_pos_items(db: Session = Depends(get_db)):
    variants = db.query(models.ProductVariant).join(models.ProductVariant.product).filter(
        models.Product.available_in_pos == True
    ).all()
    
    results = []
    for v in variants:
        cat_name = "Général"
        if v.product and getattr(v.product, "category", None) and getattr(v.product.category, "name", None):
            cat_name = v.product.category.name
            
        results.append({
            "variant_id": v.id,
            "product_name": f"{v.product.name} ({v.color or 'Std'})",
            "reference": v.reference,
            "barcode": v.barcode,
            "price": v.cost_price or 0, # Note: using cost_price as sell_price for mockup
            "stock": v.quantity_in_stock,
            "category": cat_name
        })
    return results

@router.put("/items/{variant_id}")
def update_pos_item(variant_id: int, price: float = None, stock: float = None, db: Session = Depends(get_db)):
    variant = db.query(models.ProductVariant).filter(models.ProductVariant.id == variant_id).first()
    if not variant:
        raise HTTPException(status_code=404, detail="Article non trouvé")
        
    if price is not None:
        variant.cost_price = price
    if stock is not None:
        # Note: simplistic stock update for POS Zero-UI edit. Real ERP should make a stock move.
        variant.quantity_in_stock = stock
        
    db.commit()
    return {"message": "Article mis à jour", "price": variant.cost_price, "stock": variant.quantity_in_stock}

@router.post("/sessions/open", response_model=schemas.POSSessionSchema)
def open_session(
    starting_cash: float = 0.0,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    active = db.query(models.POSSession).filter(models.POSSession.status == "OPEN").first()
    if active:
        raise HTTPException(status_code=400, detail="Une session est déjà ouverte.")
        
    date_str = datetime.now().strftime("%Y%m%d%H%M")
    ref = f"POS-S-{date_str}"
    
    new_session = models.POSSession(
        reference=ref,
        opened_by_user=current_user.get("sub", "unknown"),
        starting_cash=starting_cash,
        status="OPEN"
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return new_session

@router.post("/sessions/{session_id}/movements", response_model=schemas.POSCashMovementSchema)
def create_cash_movement(session_id: int, req: schemas.POSCashMovementRequest, db: Session = Depends(get_db)):
    session = db.query(models.POSSession).filter(models.POSSession.id == session_id).first()
    if not session or session.status == "CLOSED":
        raise HTTPException(status_code=400, detail="Session invalide ou fermée.")
        
    mv = models.POSCashMovement(
        session_id=session.id,
        movement_type=req.movement_type,
        amount=req.amount,
        reason=req.reason,
        author=req.author
    )
    db.add(mv)
    db.commit()
    db.refresh(mv)
    return mv

@router.post("/sessions/{session_id}/close")
def close_session(session_id: int, closing_cash: float, db: Session = Depends(get_db)):
    session = db.query(models.POSSession).filter(models.POSSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvée.")
    if session.status == "CLOSED":
        raise HTTPException(status_code=400, detail="Session déjà fermée.")
        
    # Calculate expected cash
    cash_orders = db.query(models.POSOrder).filter(
        models.POSOrder.session_id == session.id,
        models.POSOrder.payment_method == "CASH"
    ).all()
    total_cash_sales = sum(o.amount_total for o in cash_orders)
    
    # Calculate movements
    movements = db.query(models.POSCashMovement).filter(models.POSCashMovement.session_id == session.id).all()
    cash_in = sum(m.amount for m in movements if m.movement_type == "IN")
    cash_out = sum(m.amount for m in movements if m.movement_type == "OUT")
    
    expected_cash = session.starting_cash + total_cash_sales + cash_in - cash_out
    
    session.status = "CLOSED"
    session.closed_at = datetime.utcnow()
    session.closing_cash = closing_cash
    db.commit()
    
    difference = closing_cash - expected_cash
    
    return {
        "message": "Caisse fermée avec succès", 
        "expected": expected_cash, 
        "actual": closing_cash,
        "difference": difference
    }

@router.get("/sessions/{session_id}/report")
def get_session_report(session_id: int, db: Session = Depends(get_db)):
    session = db.query(models.POSSession).filter(models.POSSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvée.")
        
    orders = db.query(models.POSOrder).filter(models.POSOrder.session_id == session.id).all()
    total_sales = sum(o.amount_total for o in orders)
    total_cash = sum(o.amount_total for o in orders if o.payment_method == "CASH")
    total_cb = sum(o.amount_total for o in orders if o.payment_method == "CARD")
    
    movements = db.query(models.POSCashMovement).filter(models.POSCashMovement.session_id == session.id).all()
    cash_in = sum(m.amount for m in movements if m.movement_type == "IN")
    cash_out = sum(m.amount for m in movements if m.movement_type == "OUT")
    
    expected_cash = session.starting_cash + total_cash + cash_in - cash_out
    
    # Best-selling products logic
    product_sales = {}
    for o in orders:
        for line in o.lines:
            product_sales[line.product_name] = product_sales.get(line.product_name, 0) + line.quantity
            
    top_products = sorted([{"name": k, "qty": v} for k, v in product_sales.items()], key=lambda x: x["qty"], reverse=True)[:5]
    
    return {
        "session_reference": session.reference,
        "status": session.status,
        "opened_at": session.opened_at,
        "starting_cash": session.starting_cash,
        "total_sales": total_sales,
        "total_cash_collected": total_cash,
        "total_cb_collected": total_cb,
        "cash_in": cash_in,
        "cash_out": cash_out,
        "expected_cash_in_drawer": expected_cash,
        "top_products": top_products,
        "ticket_count": len(orders)
    }

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
        amount_return=amount_return,
        seller_name=req.seller_name
    )
    db.add(order)
    db.flush()
    
    global_location = db.query(models.StockLocation).filter(models.StockLocation.id == 1).first() # Default location 1
    if not global_location:
        global_location = InventoryService.get_or_create_location(db, "WH/Stock", "internal")
    customer_location = InventoryService.get_or_create_location(db, "Partner/Customer", "customer")
    
    for item in req.items:
        ol = models.POSOrderLine(
            order_id=order.id,
            variant_id=item.variant_id,
            product_name=item.product_name,
            quantity=item.quantity,
            unit_price=item.price
        )
        db.add(ol)
        
        try:
            InventoryService.move_stock(
                db,
                variant_id=item.variant_id,
                source_location_id=global_location.id,
                dest_location_id=customer_location.id,
                quantity=item.quantity,
                reference=f"POS Out - {ref}",
                author="POS System",
                notes=f"Vente Caisse Ticket {ref}",
                source_screen="pos.checkout",
                document_type="pos_order",
                document_reference=ref,
                business_reason="Vente comptoir",
            )
        except ValueError as exc:
            status_code = 423 if "Zone gelée" in str(exc) else 400
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        
        # Log to Chatter
        audit_log = models.ChatterMessage(
            model_name="variant",
            record_id=item.variant_id,
            body=f"Vente effectuée au comptoir (Caisse) - Ticket {ref}. Quantité décrémentée : {item.quantity}",
            author=req.seller_name or "Vendeur POS",
            is_system_log=True
        )
        db.add(audit_log)
        
        
    # --- AUTO-GENERATE NF525 INVOICE ---
    subtotal = amount_total / (1 + (req.tax_rate / 100.0))
    tax_amount = amount_total - subtotal
    
    new_invoice = models.Invoice(
        reference=generate_invoice_reference(db),
        sale_order_id=None,
        client_name="Client Comptoir (POS)",
        client_address="Vente au détail",
        due_date=datetime.utcnow(),
        status="PAID", # POS sales are paid immediately
        subtotal=subtotal,
        tax_rate=req.tax_rate,
        tax_amount=tax_amount,
        total=amount_total
    )
    db.add(new_invoice)
    db.flush()
    
    # Auto-Payment
    new_payment = models.Payment(
        invoice_id=new_invoice.id,
        amount=req.amount_paid if req.amount_paid <= amount_total else amount_total, # Only record what covers the invoice
        method=req.payment_method,
        reference=f"POS Ticket {ref}"
    )
    db.add(new_payment)
    
    for item in req.items:
        db_inv_line = models.InvoiceLine(
            invoice_id=new_invoice.id,
            description=item.product_name,
            quantity=item.quantity,
            unit_price=item.price / (1 + (req.tax_rate / 100.0)), # Price in POS is usually TTC, invoice line needs HT
            tax_rate=req.tax_rate
        )
        db.add(db_inv_line)
        
    new_invoice.qr_code_hash = compute_qr_seal(new_invoice)
        
    db.commit()
    db.refresh(order)
    
    # Attach NF525 ref to order temporarily if needed (we can return it in the schema, but order schema doesn't have it yet)
    # We will just return the order.
    return order

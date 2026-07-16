from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from pydantic import BaseModel
from typing import List, Optional
import uuid

from backend.database import get_db
from backend import models
from backend.core import security
from backend.services.stock_service import InventoryService

router = APIRouter(
    prefix="/v2/purchases",
    tags=["V2 Purchases"],
    dependencies=[Depends(security.get_current_user)],
)

class PurchaseOrderLineInput(BaseModel):
    variant_id: int
    quantity: float
    unit_price: float
    discount_percent: float = 0.0

class PurchaseOrderCreate(BaseModel):
    supplier: str
    expected_date: Optional[datetime] = None
    global_discount_percent: float = 0.0
    notes: Optional[str] = None
    lines: List[PurchaseOrderLineInput] = []

class PurchaseOrderReceiveInput(BaseModel):
    target_location_id: int

@router.get("/ai-recommendations")
def get_ai_recommendations(db: Session = Depends(get_db)):
    variants = db.query(models.ProductVariant).all()
    recommendations = []
    
    for v in variants:
        current_stock = float(v.quantity_in_stock or 0)
        threshold = float(v.min_threshold or 0)
        if threshold > 0 and current_stock <= threshold:
            suggested_quantity = max(threshold * 2 - current_stock, threshold)
            recommendations.append({
                "variant_id": v.id,
                "reference": v.reference,
                "product_name": v.product.name if v.product else "Article stock",
                "current_stock": current_stock,
                "suggested_quantity": suggested_quantity,
                "reason": f"Stock actuel ({current_stock:g}) inférieur ou égal au seuil configuré ({threshold:g}).",
                "confidence": 80
            })
            
    return recommendations

@router.get("/")
def get_purchase_orders(db: Session = Depends(get_db)):
    pos = db.query(models.PurchaseOrder).order_by(models.PurchaseOrder.order_date.desc()).all()
    result = []
    for po in pos:
        result.append({
            "id": po.id,
            "reference": po.reference,
            "supplier": po.supplier,
            "order_date": po.order_date,
            "expected_date": po.expected_date,
            "status": po.status,
            "total_amount": po.total_amount,
            "lines_count": len(po.lines)
        })
    return result

@router.post("/")
def create_purchase_order(
    data: PurchaseOrderCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    # Generate PO reference
    current_year = datetime.now().year
    count = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.reference.like(f"PO-{current_year}-%")).count() + 1
    ref = f"PO-{current_year}-{count:04d}"
    
    po = models.PurchaseOrder(
        reference=ref,
        supplier=data.supplier,
        expected_date=data.expected_date,
        global_discount_percent=max(0, min(float(data.global_discount_percent or 0), 100)),
        notes=data.notes,
        status=models.PurchaseOrderStatus.DRAFT,
        author=current_user.get("sub", "unknown")
    )
    db.add(po)
    db.flush()
    
    total = 0
    for line in data.lines:
        quantity = max(float(line.quantity or 0), 0)
        unit_price = max(float(line.unit_price or 0), 0)
        discount_percent = max(0, min(float(line.discount_percent or 0), 100))
        new_line = models.PurchaseOrderLine(
            order_id=po.id,
            variant_id=line.variant_id,
            quantity=quantity,
            unit_price=unit_price,
            discount_percent=discount_percent,
            quantity_received=0
        )
        db.add(new_line)
        total += quantity * unit_price * (1 - discount_percent / 100)
        
    po.total_amount = total * (1 - po.global_discount_percent / 100)
    db.commit()
    db.refresh(po)
    return {"id": po.id, "reference": po.reference}

@router.get("/{po_id}")
def get_purchase_order_details(po_id: int, db: Session = Depends(get_db)):
    po = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
        
    lines = []
    for line in po.lines:
        lines.append({
            "id": line.id,
            "variant_id": line.variant_id,
            "variant_ref": line.variant.reference if line.variant else "Inconnu",
            "product_name": line.variant.product.name if line.variant and line.variant.product else "Inconnu",
            "quantity": line.quantity,
            "quantity_received": line.quantity_received,
            "unit_price": line.unit_price,
            "discount_percent": line.discount_percent or 0,
            "line_total": (line.quantity or 0) * (line.unit_price or 0) * (1 - float(line.discount_percent or 0) / 100),
        })
        
    return {
        "id": po.id,
        "reference": po.reference,
        "supplier": po.supplier,
        "order_date": po.order_date,
        "expected_date": po.expected_date,
        "status": po.status,
        "total_amount": po.total_amount,
        "notes": po.notes,
        "author": po.author,
        "global_discount_percent": po.global_discount_percent or 0,
        "lines": lines
    }

@router.post("/{po_id}/receive")
def receive_purchase_order(po_id: int, data: PurchaseOrderReceiveInput, db: Session = Depends(get_db)):
    po = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
        
    if po.status == models.PurchaseOrderStatus.RECEIVED:
        raise HTTPException(status_code=400, detail="PO already fully received")
        
    # Get Supplier virtual location, or create if not exists
    supplier_loc = db.query(models.StockLocation).filter(models.StockLocation.usage == 'supplier').first()
    if not supplier_loc:
        supplier_loc = models.StockLocation(name="Fournisseurs", usage="supplier")
        db.add(supplier_loc)
        db.flush()
        
    all_received = True
    
    for line in po.lines:
        remaining = line.quantity - line.quantity_received
        if remaining > 0:
            ref_move = f"IN/{po.reference}/{line.id}"
            try:
                InventoryService.move_stock(
                    db,
                    variant_id=line.variant_id,
                    source_location_id=supplier_loc.id,
                    dest_location_id=data.target_location_id,
                    quantity=remaining,
                    reference=ref_move,
                    notes=f"Réception auto depuis {po.reference}",
                    author=po.author,
                    source_screen="purchases.receipt",
                    document_type="purchase_order",
                    document_reference=po.reference,
                    business_reason="Réception fournisseur",
                )
            except ValueError as exc:
                status_code = 423 if "Zone gelée" in str(exc) else 400
                raise HTTPException(status_code=status_code, detail=str(exc)) from exc
            
            line.quantity_received = line.quantity
            
    if all_received:
        po.status = models.PurchaseOrderStatus.RECEIVED
        
    db.commit()
    return {"status": "success", "po_status": po.status}

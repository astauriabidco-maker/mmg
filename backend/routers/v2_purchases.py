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
from backend.services.document_sequences import next_number
from ..core.time import utcnow

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

class PurchaseOrderReceiveLineInput(BaseModel):
    line_id: int
    quantity: float

class PurchaseOrderReceiveInput(BaseModel):
    target_location_id: int
    lines: Optional[List[PurchaseOrderReceiveLineInput]] = None

class SupplierInvoiceLineInput(BaseModel):
    purchase_order_line_id: int
    quantity: float

class SupplierInvoiceCreate(BaseModel):
    supplier_reference: Optional[str] = None
    issue_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    notes: Optional[str] = None
    lines: List[SupplierInvoiceLineInput]

def _supplier_invoice_reference(db: Session) -> str:
    # Format: FF-YYYY-XXXX — séquence transactionnelle inaltérable (NF525)
    return next_number(db, "supplier_invoice")

def _invoiced_quantities_by_po_line(db: Session, po_id: int) -> dict[int, float]:
    invoice_lines = (
        db.query(models.SupplierInvoiceLine)
        .join(models.SupplierInvoice, models.SupplierInvoiceLine.invoice_id == models.SupplierInvoice.id)
        .filter(
            models.SupplierInvoice.purchase_order_id == po_id,
            models.SupplierInvoice.status != "CANCELLED",
        )
        .all()
    )
    quantities: dict[int, float] = {}
    for line in invoice_lines:
        quantities[line.purchase_order_line_id] = quantities.get(line.purchase_order_line_id, 0.0) + float(line.quantity or 0)
    return quantities

def _serialize_supplier_invoice(invoice: models.SupplierInvoice) -> dict:
    return {
        "id": invoice.id,
        "reference": invoice.reference,
        "supplier_reference": invoice.supplier_reference,
        "issue_date": invoice.issue_date,
        "due_date": invoice.due_date,
        "status": invoice.status,
        "subtotal": invoice.subtotal,
        "discount_amount": invoice.discount_amount,
        "total_amount": invoice.total_amount,
        "notes": invoice.notes,
        "lines": [
            {
                "id": line.id,
                "purchase_order_line_id": line.purchase_order_line_id,
                "variant_id": line.variant_id,
                "description": line.description,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "discount_percent": line.discount_percent,
                "line_total": line.line_total,
            }
            for line in invoice.lines
        ],
    }

def _purchase_order_metrics(po: models.PurchaseOrder, db: Session) -> dict:
    invoiced_quantities = _invoiced_quantities_by_po_line(db, po.id)
    quantity_ordered = sum(float(line.quantity or 0) for line in po.lines)
    quantity_received = sum(float(line.quantity_received or 0) for line in po.lines)
    quantity_invoiced = sum(float(invoiced_quantities.get(line.id, 0)) for line in po.lines)
    quantity_remaining = max(quantity_ordered - quantity_received, 0)
    quantity_invoiceable = max(quantity_received - quantity_invoiced, 0)

    if po.status == models.PurchaseOrderStatus.CANCELLED:
        receipt_status = "CANCELLED"
        invoice_match_status = "CANCELLED"
        operational_status = "CANCELLED"
        next_action = "Commande annulée"
    else:
        if quantity_received <= 0:
            receipt_status = "NONE"
        elif quantity_remaining > 0:
            receipt_status = "PARTIAL"
        else:
            receipt_status = "FULL"

        if quantity_received <= 0:
            invoice_match_status = "NO_RECEIPT"
        elif quantity_invoiced <= 0:
            invoice_match_status = "TO_MATCH"
        elif quantity_invoiceable > 0:
            invoice_match_status = "PARTIAL_MATCH"
        else:
            invoice_match_status = "MATCHED"

        if quantity_ordered <= 0:
            operational_status = "DRAFT_EMPTY"
            next_action = "Ajouter des lignes d'achat"
        elif quantity_remaining > 0:
            operational_status = "TO_RECEIVE" if quantity_received <= 0 else "PARTIAL_RECEIPT"
            next_action = "Réceptionner fournisseur"
        elif quantity_invoiceable > 0:
            operational_status = "INVOICE_TO_MATCH"
            next_action = "Rapprocher facture fournisseur"
        else:
            operational_status = "READY_TO_CLOSE"
            next_action = "Clôturer après contrôle"

    return {
        "quantity_ordered": quantity_ordered,
        "quantity_received": quantity_received,
        "quantity_remaining": quantity_remaining,
        "quantity_invoiced": quantity_invoiced,
        "quantity_invoiceable": quantity_invoiceable,
        "receipt_status": receipt_status,
        "supplier_invoice_status": "FULL" if quantity_received > 0 and quantity_invoiced >= quantity_received else "PARTIAL" if quantity_invoiced > 0 else "NONE",
        "invoice_match_status": invoice_match_status,
        "operational_status": operational_status,
        "next_action": next_action,
        "invoiced_quantities": invoiced_quantities,
    }

def _line_match_status(quantity_received: float, quantity_invoiced: float) -> str:
    if quantity_received <= 0:
        return "NO_RECEIPT"
    if quantity_invoiced <= 0:
        return "TO_INVOICE"
    if quantity_invoiced < quantity_received:
        return "PARTIAL_MATCH"
    return "MATCHED"

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
        metrics = _purchase_order_metrics(po, db)
        result.append({
            "id": po.id,
            "reference": po.reference,
            "supplier": po.supplier,
            "order_date": po.order_date,
            "expected_date": po.expected_date,
            "status": po.status,
            "total_amount": po.total_amount,
            "lines_count": len(po.lines),
            "quantity_ordered": metrics["quantity_ordered"],
            "quantity_received": metrics["quantity_received"],
            "quantity_remaining": metrics["quantity_remaining"],
            "quantity_invoiced": metrics["quantity_invoiced"],
            "quantity_invoiceable": metrics["quantity_invoiceable"],
            "receipt_status": metrics["receipt_status"],
            "supplier_invoice_status": metrics["supplier_invoice_status"],
            "invoice_match_status": metrics["invoice_match_status"],
            "operational_status": metrics["operational_status"],
            "next_action": metrics["next_action"],
        })
    return result

@router.post("/")
def create_purchase_order(
    data: PurchaseOrderCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    # Generate PO reference — séquence transactionnelle (NF525)
    ref = next_number(db, "purchase_order")
    
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
        
    metrics = _purchase_order_metrics(po, db)
    invoiced_quantities = metrics["invoiced_quantities"]
    lines = []
    for line in po.lines:
        quantity_invoiced = float(invoiced_quantities.get(line.id, 0))
        quantity_received = float(line.quantity_received or 0)
        quantity_ordered = float(line.quantity or 0)
        quantity_remaining = max(quantity_ordered - quantity_received, 0)
        quantity_invoiceable = max(quantity_received - quantity_invoiced, 0)
        lines.append({
            "id": line.id,
            "variant_id": line.variant_id,
            "variant_ref": line.variant.reference if line.variant else "Inconnu",
            "product_name": line.variant.product.name if line.variant and line.variant.product else "Inconnu",
            "quantity": quantity_ordered,
            "quantity_received": quantity_received,
            "quantity_remaining": quantity_remaining,
            "quantity_invoiced": quantity_invoiced,
            "quantity_invoiceable": quantity_invoiceable,
            "unit_price": line.unit_price,
            "discount_percent": line.discount_percent or 0,
            "line_total": (line.quantity or 0) * float(line.unit_price or 0) * (1 - float(line.discount_percent or 0) / 100),
            "receipt_status": "RECEIVED" if quantity_remaining <= 0 and quantity_ordered > 0 else "PARTIAL" if quantity_received > 0 else "TO_RECEIVE",
            "invoice_match_status": _line_match_status(quantity_received, quantity_invoiced),
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
        "quantity_ordered": metrics["quantity_ordered"],
        "quantity_received": metrics["quantity_received"],
        "quantity_remaining": metrics["quantity_remaining"],
        "quantity_invoiced": metrics["quantity_invoiced"],
        "quantity_invoiceable": metrics["quantity_invoiceable"],
        "receipt_status": metrics["receipt_status"],
        "supplier_invoice_status": metrics["supplier_invoice_status"],
        "invoice_match_status": metrics["invoice_match_status"],
        "operational_status": metrics["operational_status"],
        "next_action": metrics["next_action"],
        "lines": lines,
        "supplier_invoices": [_serialize_supplier_invoice(invoice) for invoice in po.supplier_invoices],
    }

@router.post("/{po_id}/receive")
def receive_purchase_order(
    po_id: int,
    data: PurchaseOrderReceiveInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    security.assert_permission(db, current_user, "purchases.receive")
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
        
    requested_lines = {line.line_id: float(line.quantity or 0) for line in (data.lines or [])}
    if data.lines:
        po_line_ids = {line.id for line in po.lines}
        unknown_line_ids = sorted(set(requested_lines.keys()) - po_line_ids)
        if unknown_line_ids:
            raise HTTPException(status_code=400, detail=f"Ligne(s) inconnue(s): {unknown_line_ids}")

    received_lines = 0
    received_quantity = 0.0
    
    for line in po.lines:
        remaining = line.quantity - line.quantity_received
        if remaining <= 0:
            continue

        receive_qty = remaining if not data.lines else requested_lines.get(line.id, 0)
        if receive_qty <= 0:
            continue
        if receive_qty > remaining:
            raise HTTPException(
                status_code=400,
                detail=f"Quantité reçue supérieure au reste à recevoir pour la ligne {line.id}.",
            )

        if receive_qty > 0:
            ref_move = f"IN/{po.reference}/{line.id}"
            try:
                InventoryService.move_stock(
                    db,
                    variant_id=line.variant_id,
                    source_location_id=supplier_loc.id,
                    dest_location_id=data.target_location_id,
                    quantity=receive_qty,
                    reference=ref_move,
                    notes=f"Réception fournisseur depuis {po.reference}",
                    author=current_user.get("sub", "unknown"),
                    source_screen="purchases.receipt",
                    document_type="purchase_order",
                    document_reference=po.reference,
                    business_reason="Réception fournisseur",
                )
            except ValueError as exc:
                status_code = 423 if "Zone gelée" in str(exc) else 400
                raise HTTPException(status_code=status_code, detail=str(exc)) from exc
            
            line.quantity_received += receive_qty
            received_lines += 1
            received_quantity += receive_qty
            
    if received_lines == 0:
        raise HTTPException(status_code=400, detail="Aucune quantité à réceptionner.")

    if all((line.quantity_received or 0) >= (line.quantity or 0) for line in po.lines):
        po.status = models.PurchaseOrderStatus.RECEIVED
    elif any((line.quantity_received or 0) > 0 for line in po.lines):
        po.status = models.PurchaseOrderStatus.PARTIAL
        
    db.commit()
    return {
        "status": "success",
        "po_status": po.status,
        "received_lines": received_lines,
        "received_quantity": received_quantity,
    }

@router.post("/{po_id}/supplier-invoices")
def create_supplier_invoice(
    po_id: int,
    data: SupplierInvoiceCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    po = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    if not data.lines:
        raise HTTPException(status_code=400, detail="La facture fournisseur doit contenir au moins une ligne.")

    po_lines = {line.id: line for line in po.lines}
    requested = {}
    for line in data.lines:
        if line.purchase_order_line_id not in po_lines:
            raise HTTPException(status_code=400, detail=f"Ligne d'achat inconnue: {line.purchase_order_line_id}.")
        quantity = float(line.quantity or 0)
        if quantity <= 0:
            continue
        requested[line.purchase_order_line_id] = requested.get(line.purchase_order_line_id, 0.0) + quantity

    if not requested:
        raise HTTPException(status_code=400, detail="Aucune quantité positive à facturer.")

    already_invoiced = _invoiced_quantities_by_po_line(db, po.id)
    for line_id, quantity in requested.items():
        po_line = po_lines[line_id]
        invoiceable = max(float(po_line.quantity_received or 0) - float(already_invoiced.get(line_id, 0)), 0)
        if quantity > invoiceable:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Facture fournisseur impossible: quantité facturée ({quantity:g}) "
                    f"supérieure au reçu non facturé ({invoiceable:g}) pour la ligne {line_id}."
                ),
            )

    invoice = models.SupplierInvoice(
        reference=_supplier_invoice_reference(db),
        supplier_reference=data.supplier_reference,
        purchase_order_id=po.id,
        supplier=po.supplier,
        issue_date=data.issue_date or utcnow(),
        due_date=data.due_date,
        status="TO_PAY",
        notes=data.notes,
        author=current_user.get("sub", "unknown"),
    )
    db.add(invoice)
    db.flush()

    subtotal_before_global = 0.0
    for line_id, quantity in requested.items():
        po_line = po_lines[line_id]
        discount_percent = max(0, min(float(po_line.discount_percent or 0), 100))
        line_total = quantity * float(po_line.unit_price or 0) * (1 - discount_percent / 100)
        description = po_line.variant.product.name if po_line.variant and po_line.variant.product else po_line.variant.reference if po_line.variant else "Article fournisseur"
        db.add(models.SupplierInvoiceLine(
            invoice_id=invoice.id,
            purchase_order_line_id=po_line.id,
            variant_id=po_line.variant_id,
            description=description,
            quantity=quantity,
            unit_price=po_line.unit_price,
            discount_percent=discount_percent,
            line_total=line_total,
        ))
        subtotal_before_global += line_total

    global_discount_percent = max(0, min(float(po.global_discount_percent or 0), 100))
    invoice.subtotal = subtotal_before_global
    invoice.discount_amount = subtotal_before_global * (global_discount_percent / 100)
    invoice.total_amount = invoice.subtotal - invoice.discount_amount
    db.commit()
    db.refresh(invoice)
    return _serialize_supplier_invoice(invoice)

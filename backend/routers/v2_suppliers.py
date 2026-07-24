from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import List, Optional

from backend.database import get_db
from backend import models
from backend.core import security
from ..core.time import utcnow

router = APIRouter(
    prefix="/v2/suppliers",
    tags=["V2 Suppliers"],
    dependencies=[Depends(security.get_current_user)],
)

class SupplierBase(BaseModel):
    name: str
    contact_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    country: Optional[str] = None
    tax_id: Optional[str] = None
    supplier_status: str = "ACTIVE"
    supplier_category: Optional[str] = None
    default_currency: str = "EUR"
    incoterm: Optional[str] = None
    delivery_terms: Optional[str] = None
    website: Optional[str] = None
    payment_terms: Optional[str] = None
    lead_time_days: Optional[int] = None
    preferred_contact_method: Optional[str] = None
    notes: Optional[str] = None

class SupplierCreate(SupplierBase):
    pass

@router.get("/")
def get_suppliers(db: Session = Depends(get_db)):
    return db.query(models.Supplier).filter(models.Supplier.is_active == True).order_by(models.Supplier.name).all()

@router.post("/")
def create_supplier(supplier: SupplierCreate, db: Session = Depends(get_db)):
    db_sup = db.query(models.Supplier).filter(models.Supplier.name == supplier.name).first()
    if db_sup:
        raise HTTPException(status_code=400, detail="Supplier already exists")
    
    new_sup = models.Supplier(**supplier.model_dump())
    db.add(new_sup)
    db.commit()
    db.refresh(new_sup)
    return new_sup

def _supplier_po_metrics(po: models.PurchaseOrder, invoiced_quantities: dict[int, float]) -> dict:
    quantity_ordered = sum(float(line.quantity or 0) for line in po.lines)
    quantity_received = sum(float(line.quantity_received or 0) for line in po.lines)
    quantity_invoiced = sum(float(invoiced_quantities.get(line.id, 0)) for line in po.lines)
    quantity_remaining = max(quantity_ordered - quantity_received, 0)
    quantity_invoiceable = max(quantity_received - quantity_invoiced, 0)
    is_cancelled = po.status == models.PurchaseOrderStatus.CANCELLED
    is_late = bool(
        po.expected_date
        and po.expected_date.date() < utcnow().date()
        and quantity_remaining > 0
        and not is_cancelled
    )
    late_days = (utcnow().date() - po.expected_date.date()).days if is_late and po.expected_date else 0

    if is_cancelled:
        operational_status = "CANCELLED"
        next_action = "Commande annulée"
    elif quantity_ordered <= 0:
        operational_status = "DRAFT_EMPTY"
        next_action = "Ajouter des lignes d'achat"
    elif quantity_remaining > 0:
        operational_status = "LATE_RECEIPT" if is_late else "TO_RECEIVE"
        next_action = "Relancer fournisseur" if is_late else "Réceptionner fournisseur"
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
        "is_late": is_late,
        "late_days": late_days,
        "operational_status": operational_status,
        "next_action": next_action,
    }


def _supplier_invoiced_quantities(db: Session, po_ids: list[int]) -> dict[int, float]:
    if not po_ids:
        return {}
    rows = (
        db.query(
            models.SupplierInvoiceLine.purchase_order_line_id,
            func.sum(models.SupplierInvoiceLine.quantity),
        )
        .join(models.SupplierInvoice, models.SupplierInvoiceLine.invoice_id == models.SupplierInvoice.id)
        .filter(
            models.SupplierInvoice.purchase_order_id.in_(po_ids),
            models.SupplierInvoice.status != "CANCELLED",
        )
        .group_by(models.SupplierInvoiceLine.purchase_order_line_id)
        .all()
    )
    return {line_id: float(quantity or 0) for line_id, quantity in rows}


def _supplier_order_payload(po: models.PurchaseOrder, metrics: dict) -> dict:
    return {
        "id": po.id,
        "reference": po.reference,
        "order_date": po.order_date,
        "expected_date": po.expected_date,
        "status": po.status,
        "total_amount": float(po.total_amount or 0),
        "lines_count": len(po.lines),
        "quantity_ordered": metrics["quantity_ordered"],
        "quantity_received": metrics["quantity_received"],
        "quantity_remaining": metrics["quantity_remaining"],
        "quantity_invoiced": metrics["quantity_invoiced"],
        "quantity_invoiceable": metrics["quantity_invoiceable"],
        "is_late": metrics["is_late"],
        "late_days": metrics["late_days"],
        "operational_status": metrics["operational_status"],
        "next_action": metrics["next_action"],
    }


def _supplier_quality_score(
    supplier: models.Supplier,
    orders: list[dict],
    disputes: list[models.SupplierDispute],
    invoices: list[models.SupplierInvoice],
) -> dict:
    open_disputes = [dispute for dispute in disputes if dispute.status in {"OPEN", "IN_PROGRESS"}]
    resolved_disputes = [dispute for dispute in disputes if dispute.status == "RESOLVED"]
    quality_disputes = [dispute for dispute in disputes if dispute.category == "QUALITY"]
    quantity_disputes = [dispute for dispute in disputes if dispute.category == "QUANTITY"]
    open_blocking_disputes = [
        dispute
        for dispute in open_disputes
        if dispute.severity in {"HIGH", "BLOCKING", "CRITICAL"} or dispute.blocks_receipt or dispute.blocks_payment
    ]
    payment_blockers = [dispute for dispute in open_disputes if dispute.blocks_payment]
    late_orders = [order for order in orders if order["is_late"]]
    partial_orders = [order for order in orders if order["status"] == models.PurchaseOrderStatus.PARTIAL]
    received_orders = [order for order in orders if order["status"] == models.PurchaseOrderStatus.RECEIVED]
    active_orders = [order for order in orders if order["status"] != models.PurchaseOrderStatus.CANCELLED]
    overdue_invoices = [
        invoice for invoice in invoices
        if invoice.status in {"TO_PAY", "PARTIAL"}
        and invoice.due_date
        and invoice.due_date.date() < utcnow().date()
    ]

    disputed_po_ids = {
        dispute.purchase_order_id
        for dispute in disputes
        if dispute.purchase_order_id and dispute.category in {"QUALITY", "QUANTITY"}
    }
    conforming_received_orders = [
        order for order in received_orders
        if order["id"] not in disputed_po_ids
    ]
    conformity_rate = (
        round((len(conforming_received_orders) / len(received_orders)) * 100, 1)
        if received_orders else None
    )
    delivery_rate = (
        round((len(received_orders) / len(active_orders)) * 100, 1)
        if active_orders else None
    )

    penalties = []

    def add_penalty(code: str, label: str, points: int, count: int = 1):
        if count <= 0:
            return
        penalties.append({
            "code": code,
            "label": label,
            "points": points * count,
            "count": count,
        })

    add_penalty("supplier.blocked", "Fournisseur bloqué", 40, 1 if supplier.supplier_status == "BLOCKED" else 0)
    add_penalty("late_orders", "Commandes en retard", 8, len(late_orders))
    add_penalty("open_disputes", "Litiges ouverts", 10, len(open_disputes))
    add_penalty("blocking_disputes", "Litiges bloquants", 12, len(open_blocking_disputes))
    add_penalty("quality_disputes", "Non-conformités qualité", 8, len(quality_disputes))
    add_penalty("quantity_disputes", "Écarts de quantité", 6, len(quantity_disputes))
    add_penalty("partial_orders", "Réceptions partielles", 4, len(partial_orders))
    add_penalty("payment_blockers", "Paiements bloqués", 8, len(payment_blockers))
    add_penalty("overdue_invoices", "Factures échues non payées", 3, len(overdue_invoices))

    score = max(0, 100 - sum(penalty["points"] for penalty in penalties))
    if score >= 85:
        label = "Fiable"
        recommendation = "Commander normalement, surveillance standard."
        tone = "emerald"
    elif score >= 70:
        label = "À surveiller"
        recommendation = "Commander possible, contrôler délais et factures ouvertes."
        tone = "orange"
    elif score >= 50:
        label = "Risque fournisseur"
        recommendation = "Commander avec validation achats et suivi rapproché."
        tone = "red"
    else:
        label = "Critique"
        recommendation = "Éviter tout nouvel engagement avant résolution des points bloquants."
        tone = "red"

    return {
        "score": score,
        "label": label,
        "tone": tone,
        "recommendation": recommendation,
        "conformity_rate": conformity_rate,
        "delivery_rate": delivery_rate,
        "late_orders": len(late_orders),
        "open_disputes": len(open_disputes),
        "resolved_disputes": len(resolved_disputes),
        "quality_disputes": len(quality_disputes),
        "quantity_disputes": len(quantity_disputes),
        "payment_blockers": len(payment_blockers),
        "overdue_invoices": len(overdue_invoices),
        "partial_orders": len(partial_orders),
        "penalties": penalties,
    }


@router.get("/{supplier_id}/operations")
def get_supplier_operations(supplier_id: int, db: Session = Depends(get_db)):
    supplier = (
        db.query(models.Supplier)
        .filter(models.Supplier.id == supplier_id, models.Supplier.is_active == True)
        .first()
    )
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    purchase_orders = (
        db.query(models.PurchaseOrder)
        .filter(models.PurchaseOrder.supplier == supplier.name)
        .order_by(models.PurchaseOrder.order_date.desc())
        .all()
    )
    po_ids = [po.id for po in purchase_orders]
    po_refs = [po.reference for po in purchase_orders]
    invoiced_quantities = _supplier_invoiced_quantities(db, po_ids)

    orders = []
    open_orders = []
    to_receive = []
    to_invoice = []
    late_orders = []
    amount_committed = 0.0
    for po in purchase_orders:
        metrics = _supplier_po_metrics(po, invoiced_quantities)
        payload = _supplier_order_payload(po, metrics)
        orders.append(payload)

        if po.status != models.PurchaseOrderStatus.CANCELLED and metrics["operational_status"] != "READY_TO_CLOSE":
            open_orders.append(payload)
            amount_committed += float(po.total_amount or 0)
        if metrics["quantity_remaining"] > 0 and po.status != models.PurchaseOrderStatus.CANCELLED:
            to_receive.append(payload)
        if metrics["quantity_invoiceable"] > 0 and po.status != models.PurchaseOrderStatus.CANCELLED:
            to_invoice.append(payload)
        if metrics["is_late"]:
            late_orders.append(payload)

    stock_moves = []
    if po_refs:
        stock_moves = (
            db.query(models.StockMove)
            .filter(
                models.StockMove.document_type == "purchase_order",
                models.StockMove.document_reference.in_(po_refs),
            )
            .order_by(models.StockMove.date.desc())
            .limit(30)
            .all()
        )

    invoices = (
        db.query(models.SupplierInvoice)
        .filter(models.SupplierInvoice.supplier == supplier.name)
        .order_by(models.SupplierInvoice.issue_date.desc())
        .limit(30)
        .all()
    )
    disputes = (
        db.query(models.SupplierDispute)
        .filter(models.SupplierDispute.supplier == supplier.name)
        .order_by(models.SupplierDispute.created_at.desc(), models.SupplierDispute.id.desc())
        .all()
    )
    open_disputes = [dispute for dispute in disputes if dispute.status in {"OPEN", "IN_PROGRESS"}]
    quality_score = _supplier_quality_score(supplier, orders, disputes, invoices)

    timeline = []
    for po in purchase_orders[:30]:
        timeline.append({
            "type": "purchase_order",
            "label": "Commande fournisseur créée",
            "reference": po.reference,
            "date": po.order_date,
            "status": po.status,
            "amount": float(po.total_amount or 0),
        })
        metrics = _supplier_po_metrics(po, invoiced_quantities)
        if metrics["is_late"]:
            timeline.append({
                "type": "late_receipt",
                "label": "Réception fournisseur en retard",
                "reference": po.reference,
                "date": po.expected_date,
                "status": "LATE",
                "quantity_remaining": metrics["quantity_remaining"],
                "late_days": metrics["late_days"],
            })

    for move in stock_moves:
        timeline.append({
            "type": "stock_receipt",
            "label": "Réception stock",
            "reference": move.reference,
            "document_reference": move.document_reference,
            "date": move.date,
            "quantity": move.quantity,
            "author": move.author,
        })

    for invoice in invoices:
        paid_amount = sum(float(payment.amount or 0) for payment in invoice.payments)
        timeline.append({
            "type": "supplier_invoice",
            "label": "Facture fournisseur enregistrée",
            "reference": invoice.reference,
            "supplier_reference": invoice.supplier_reference,
            "date": invoice.issue_date,
            "status": invoice.status,
            "amount": float(invoice.total_amount or 0),
            "paid_amount": paid_amount,
        })

    for dispute in disputes:
        timeline.append({
            "type": "supplier_dispute",
            "label": "Litige fournisseur" if dispute.status != "RESOLVED" else "Litige fournisseur résolu",
            "reference": dispute.reference,
            "date": dispute.created_at,
            "status": dispute.status,
            "severity": dispute.severity,
            "title": dispute.title,
            "purchase_order_id": dispute.purchase_order_id,
        })

    timeline.sort(key=lambda event: event["date"] or utcnow(), reverse=True)

    return {
        "supplier": {
            "id": supplier.id,
            "name": supplier.name,
            "contact_name": supplier.contact_name,
            "email": supplier.email,
            "phone": supplier.phone,
            "address": supplier.address,
            "country": supplier.country,
            "tax_id": supplier.tax_id,
            "supplier_status": supplier.supplier_status,
            "supplier_category": supplier.supplier_category,
            "default_currency": supplier.default_currency,
            "incoterm": supplier.incoterm,
            "delivery_terms": supplier.delivery_terms,
            "payment_terms": supplier.payment_terms,
            "lead_time_days": supplier.lead_time_days,
            "preferred_contact_method": supplier.preferred_contact_method,
            "website": supplier.website,
            "notes": supplier.notes,
        },
        "metrics": {
            "open_orders": len(open_orders),
            "to_receive": len(to_receive),
            "to_invoice": len(to_invoice),
            "late_orders": len(late_orders),
            "disputes": len(open_disputes),
            "amount_committed": amount_committed,
        },
        "quality_score": quality_score,
        "actions": [
            {"code": "purchase.create", "label": "Créer commande fournisseur", "enabled": supplier.supplier_status != "BLOCKED"},
            {"code": "purchase.receive", "label": "Réceptionner", "enabled": len(to_receive) > 0},
            {"code": "purchase.match_invoice", "label": "Rapprocher facture", "enabled": len(to_invoice) > 0},
            {"code": "supplier.contact", "label": "Contacter", "enabled": bool(supplier.email or supplier.phone)},
            {"code": "supplier.dispute", "label": "Ajouter litige", "enabled": True},
        ],
        "open_orders": open_orders,
        "to_receive": to_receive,
        "to_invoice": to_invoice,
        "late_orders": late_orders,
        "recent_invoices": [
            {
                "id": invoice.id,
                "reference": invoice.reference,
                "supplier_reference": invoice.supplier_reference,
                "purchase_order_id": invoice.purchase_order_id,
                "issue_date": invoice.issue_date,
                "due_date": invoice.due_date,
                "status": invoice.status,
                "total_amount": float(invoice.total_amount or 0),
                "paid_amount": sum(float(payment.amount or 0) for payment in invoice.payments),
                "remaining_amount": max(float(invoice.total_amount or 0) - sum(float(payment.amount or 0) for payment in invoice.payments), 0),
            }
            for invoice in invoices
        ],
        "disputes": [
            {
                "id": dispute.id,
                "reference": dispute.reference,
                "purchase_order_id": dispute.purchase_order_id,
                "supplier_invoice_id": dispute.supplier_invoice_id,
                "title": dispute.title,
                "description": dispute.description,
                "category": dispute.category,
                "severity": dispute.severity,
                "status": dispute.status,
                "expected_quantity": dispute.expected_quantity,
                "received_quantity": dispute.received_quantity,
                "expected_unit_price": float(dispute.expected_unit_price) if dispute.expected_unit_price is not None else None,
                "invoiced_unit_price": float(dispute.invoiced_unit_price) if dispute.invoiced_unit_price is not None else None,
                "expected_action": dispute.expected_action,
                "due_date": dispute.due_date,
                "blocks_receipt": bool(dispute.blocks_receipt),
                "blocks_payment": bool(dispute.blocks_payment),
                "impact_summary": dispute.impact_summary,
                "created_by": dispute.created_by,
                "created_at": dispute.created_at,
                "closed_at": dispute.closed_at,
                "resolution_notes": dispute.resolution_notes,
            }
            for dispute in disputes[:8]
        ],
        "recent_stock_receipts": [
            {
                "id": move.id,
                "reference": move.reference,
                "date": move.date,
                "variant_id": move.variant_id,
                "quantity": move.quantity,
                "author": move.author,
                "document_reference": move.document_reference,
                "business_reason": move.business_reason,
            }
            for move in stock_moves
        ],
        "timeline": timeline[:40],
    }

@router.put("/{supplier_id}")
def update_supplier(supplier_id: int, supplier: SupplierCreate, db: Session = Depends(get_db)):
    db_sup = db.query(models.Supplier).filter(models.Supplier.id == supplier_id).first()
    if not db_sup:
        raise HTTPException(status_code=404, detail="Supplier not found")
        
    for key, value in supplier.model_dump().items():
        setattr(db_sup, key, value)
        
    db.commit()
    db.refresh(db_sup)
    return db_sup

@router.delete("/{supplier_id}")
def delete_supplier(supplier_id: int, db: Session = Depends(get_db)):
    db_sup = db.query(models.Supplier).filter(models.Supplier.id == supplier_id).first()
    if not db_sup:
        raise HTTPException(status_code=404, detail="Supplier not found")
        
    db_sup.is_active = False # Soft delete
    db.commit()
    return {"status": "deleted"}

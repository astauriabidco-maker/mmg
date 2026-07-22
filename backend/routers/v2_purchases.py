from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import List, Optional
import uuid

from backend.database import get_db
from backend import models
from backend.core import security
from backend.services.stock_service import InventoryService
from backend.services.stock_reservations import active_reserved_quantity, physical_quantity_all_internal
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
    need_priority: Optional[str] = None
    need_reason: Optional[str] = None

class PurchaseOrderCreate(BaseModel):
    supplier: str
    expected_date: Optional[datetime] = None
    global_discount_percent: float = 0.0
    notes: Optional[str] = None
    lines: List[PurchaseOrderLineInput] = []

class PurchaseRequestCreate(PurchaseOrderCreate):
    sensitivity_reason: Optional[str] = None

class PurchaseRequestRejectInput(BaseModel):
    reason: str

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

def _purchase_request_reference(db: Session) -> str:
    return next_number(db, "purchase_request")

def _line_total(quantity: float, unit_price: float, discount_percent: float) -> float:
    return quantity * unit_price * (1 - discount_percent / 100)

def _purchase_payload_total(data: PurchaseOrderCreate) -> float:
    subtotal = 0.0
    for line in data.lines:
        quantity = max(float(line.quantity or 0), 0)
        unit_price = max(float(line.unit_price or 0), 0)
        discount_percent = max(0, min(float(line.discount_percent or 0), 100))
        subtotal += _line_total(quantity, unit_price, discount_percent)
    global_discount_percent = max(0, min(float(data.global_discount_percent or 0), 100))
    return subtotal * (1 - global_discount_percent / 100)

def _serialize_purchase_request(request: models.PurchaseRequest) -> dict:
    return {
        "id": request.id,
        "reference": request.reference,
        "supplier": request.supplier,
        "expected_date": request.expected_date,
        "status": request.status,
        "total_amount": request.total_amount,
        "global_discount_percent": request.global_discount_percent or 0,
        "sensitivity_reason": request.sensitivity_reason,
        "notes": request.notes,
        "requested_by": request.requested_by,
        "approved_by": request.approved_by,
        "approved_at": request.approved_at,
        "rejected_by": request.rejected_by,
        "rejected_at": request.rejected_at,
        "rejection_reason": request.rejection_reason,
        "converted_by": request.converted_by,
        "converted_at": request.converted_at,
        "purchase_order_id": request.purchase_order_id,
        "created_at": request.created_at,
        "updated_at": request.updated_at,
        "lines_count": len(request.lines),
        "lines": [
            {
                "id": line.id,
                "variant_id": line.variant_id,
                "variant_ref": line.variant.reference if line.variant else "Inconnu",
                "product_name": line.variant.product.name if line.variant and line.variant.product else "Article fournisseur",
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "discount_percent": line.discount_percent or 0,
                "line_total": _line_total(float(line.quantity or 0), float(line.unit_price or 0), float(line.discount_percent or 0)),
                "need_priority": line.need_priority,
                "need_reason": line.need_reason,
            }
            for line in request.lines
        ],
    }

def _create_purchase_order_from_data(
    data: PurchaseOrderCreate,
    db: Session,
    author: str,
) -> models.PurchaseOrder:
    ref = next_number(db, "purchase_order")
    po = models.PurchaseOrder(
        reference=ref,
        supplier=data.supplier,
        expected_date=data.expected_date,
        global_discount_percent=max(0, min(float(data.global_discount_percent or 0), 100)),
        notes=data.notes,
        status=models.PurchaseOrderStatus.DRAFT,
        author=author,
    )
    db.add(po)
    db.flush()

    total = 0.0
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
            quantity_received=0,
        )
        db.add(new_line)
        total += _line_total(quantity, unit_price, discount_percent)

    po.total_amount = total * (1 - po.global_discount_percent / 100)
    return po

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
    is_cancelled = po.status == models.PurchaseOrderStatus.CANCELLED
    late_days = 0
    if po.expected_date and quantity_remaining > 0 and not is_cancelled:
        late_days = max((utcnow().date() - po.expected_date.date()).days, 0)
    is_late = late_days > 0

    if is_cancelled:
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
            operational_status = "LATE_RECEIPT" if is_late else "TO_RECEIVE" if quantity_received <= 0 else "PARTIAL_RECEIPT"
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
        "receipt_status": receipt_status,
        "supplier_invoice_status": "FULL" if quantity_received > 0 and quantity_invoiced >= quantity_received else "PARTIAL" if quantity_invoiced > 0 else "NONE",
        "invoice_match_status": invoice_match_status,
        "operational_status": operational_status,
        "next_action": next_action,
        "is_late": is_late,
        "late_days": late_days,
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

def _supplier_map(db: Session) -> dict[str, models.Supplier]:
    return {
        supplier.name.upper(): supplier
        for supplier in db.query(models.Supplier).all()
    }

def _open_purchase_remaining_by_variant(db: Session) -> dict[int, float]:
    lines = (
        db.query(models.PurchaseOrderLine)
        .join(models.PurchaseOrder, models.PurchaseOrderLine.order_id == models.PurchaseOrder.id)
        .filter(models.PurchaseOrder.status != models.PurchaseOrderStatus.CANCELLED)
        .all()
    )
    incoming: dict[int, float] = {}
    for line in lines:
        remaining = max(float(line.quantity or 0) - float(line.quantity_received or 0), 0.0)
        if remaining > 0:
            incoming[line.variant_id] = incoming.get(line.variant_id, 0.0) + remaining
    return incoming

def _open_purchase_request_quantity_by_variant(db: Session) -> dict[int, float]:
    lines = (
        db.query(models.PurchaseRequestLine)
        .join(models.PurchaseRequest, models.PurchaseRequestLine.request_id == models.PurchaseRequest.id)
        .filter(models.PurchaseRequest.status.in_([
            models.PurchaseRequestStatus.PENDING_APPROVAL,
            models.PurchaseRequestStatus.APPROVED,
        ]))
        .all()
    )
    requested: dict[int, float] = {}
    for line in lines:
        quantity = max(float(line.quantity or 0), 0.0)
        if quantity > 0:
            requested[line.variant_id] = requested.get(line.variant_id, 0.0) + quantity
    return requested

def _need_priority(available_quantity: float, min_threshold: float, net_need_quantity: float) -> str:
    if net_need_quantity <= 0:
        return "COVERED"
    if available_quantity <= 0:
        return "CRITICAL"
    if min_threshold > 0 and available_quantity < min_threshold:
        return "URGENT"
    return "TO_PLAN"

def _need_origins(
    available_quantity: float,
    reserved_quantity: float,
    min_threshold: float,
    incoming_purchase_quantity: float,
    open_request_quantity: float = 0.0,
) -> list[str]:
    origins = []
    if available_quantity <= 0:
        origins.append("OUT_OF_STOCK")
    if min_threshold > 0 and available_quantity < min_threshold:
        origins.append("UNDER_MIN_THRESHOLD")
    if reserved_quantity > 0:
        origins.append("ACTIVE_RESERVATIONS")
    if incoming_purchase_quantity > 0:
        origins.append("OPEN_PURCHASE_ORDER")
    if open_request_quantity > 0:
        origins.append("OPEN_PURCHASE_REQUEST")
    return origins

def _need_reason(
    priority: str,
    available_quantity: float,
    reserved_quantity: float,
    min_threshold: float,
    incoming_purchase_quantity: float,
    open_request_quantity: float = 0.0,
) -> str:
    parts = []
    if priority == "CRITICAL":
        parts.append("Disponible nul ou négatif")
    elif priority == "URGENT":
        parts.append("Disponible sous seuil mini")
    elif priority == "COVERED":
        parts.append("Besoin couvert par commande fournisseur ouverte")
    else:
        parts.append("Disponible proche du seuil")
    if reserved_quantity > 0:
        parts.append(f"{reserved_quantity:g} unité(s) déjà réservée(s)")
    if incoming_purchase_quantity > 0:
        parts.append(f"{incoming_purchase_quantity:g} unité(s) déjà commandée(s)")
    if open_request_quantity > 0:
        parts.append(f"{open_request_quantity:g} unité(s) en demande d'achat")
    if min_threshold > 0:
        parts.append(f"seuil {min_threshold:g}")
    return " · ".join(parts)

def _recommend_purchase_quantity(
    available_quantity: float,
    min_threshold: float,
    incoming_purchase_quantity: float,
    open_request_quantity: float = 0.0,
) -> float:
    if min_threshold <= 0:
        return max(1.0 - available_quantity - incoming_purchase_quantity - open_request_quantity, 0.0)
    target_quantity = min_threshold * 2
    return max(target_quantity - available_quantity - incoming_purchase_quantity - open_request_quantity, 0.0)

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

@router.get("/needs")
@router.get("/procurement-needs")
def get_procurement_needs(
    include_covered: bool = True,
    db: Session = Depends(get_db),
):
    suppliers = _supplier_map(db)
    incoming_by_variant = _open_purchase_remaining_by_variant(db)
    open_requests_by_variant = _open_purchase_request_quantity_by_variant(db)
    needs = []

    variants = (
        db.query(models.ProductVariant)
        .join(models.Product)
        .filter(
            models.Product.product_type != "service",
            models.Product.catalog_status == "ACTIVE",
        )
        .order_by(models.Product.supplier, models.Product.name, models.ProductVariant.reference)
        .all()
    )

    for variant in variants:
        product = variant.product
        if not product:
            continue
        min_threshold = float(variant.min_threshold or 0)
        physical_quantity = physical_quantity_all_internal(db, variant)
        reserved_quantity = active_reserved_quantity(db, variant.id)
        available_quantity = max(physical_quantity - reserved_quantity, 0.0)
        incoming_purchase_quantity = float(incoming_by_variant.get(variant.id, 0.0))
        open_request_quantity = float(open_requests_by_variant.get(variant.id, 0.0))

        is_near_threshold = min_threshold > 0 and available_quantity <= min_threshold * 1.25
        if available_quantity > 0 and not is_near_threshold:
            continue
        if min_threshold <= 0 and available_quantity > 0:
            continue
        gross_need_quantity = max((min_threshold * 2 if min_threshold > 0 else 1.0) - available_quantity, 0.0)
        net_need_quantity = max(gross_need_quantity - incoming_purchase_quantity - open_request_quantity, 0.0)
        if net_need_quantity <= 0 and not include_covered:
            continue

        supplier_name = (product.supplier or "").strip()
        supplier = suppliers.get(supplier_name.upper()) if supplier_name else None
        supplier_status = supplier.supplier_status if supplier else None
        is_supplier_blocked = supplier_status == "BLOCKED" or bool(supplier and not supplier.is_active)
        is_orderable = bool(supplier_name) and supplier is not None and not is_supplier_blocked and net_need_quantity > 0
        priority = _need_priority(available_quantity, min_threshold, net_need_quantity)
        suggested_quantity = _recommend_purchase_quantity(
            available_quantity,
            min_threshold,
            incoming_purchase_quantity,
            open_request_quantity,
        )

        if not supplier_name:
            blocked_reason = "Aucun fournisseur renseigné sur l'article."
        elif supplier is None:
            blocked_reason = "Fournisseur absent du référentiel fournisseurs."
        elif is_supplier_blocked:
            blocked_reason = "Fournisseur bloqué."
        else:
            blocked_reason = None

        needs.append({
            "variant_id": variant.id,
            "product_id": product.id,
            "reference": variant.reference,
            "supplier_reference": variant.supplier_reference,
            "product_name": product.name,
            "material_type": product.material_type,
            "unit": product.unit,
            "supplier": supplier_name or None,
            "supplier_id": supplier.id if supplier else None,
            "supplier_status": supplier_status,
            "supplier_category": supplier.supplier_category if supplier else None,
            "supplier_lead_time_days": supplier.lead_time_days if supplier else None,
            "physical_quantity": physical_quantity,
            "reserved_quantity": reserved_quantity,
            "available_quantity": available_quantity,
            "min_threshold": min_threshold,
            "incoming_purchase_quantity": incoming_purchase_quantity,
            "open_purchase_request_quantity": open_request_quantity,
            "gross_need_quantity": gross_need_quantity,
            "net_need_quantity": net_need_quantity,
            "suggested_quantity": suggested_quantity,
            "priority": priority,
            "origins": _need_origins(
                available_quantity,
                reserved_quantity,
                min_threshold,
                incoming_purchase_quantity,
                open_request_quantity,
            ),
            "reason": _need_reason(
                priority,
                available_quantity,
                reserved_quantity,
                min_threshold,
                incoming_purchase_quantity,
                open_request_quantity,
            ),
            "is_orderable": is_orderable,
            "blocked_reason": blocked_reason,
            "recommended_action": (
                "Créer bon fournisseur"
                if is_orderable
                else "Suivre réception fournisseur"
                if net_need_quantity <= 0 and incoming_purchase_quantity > 0
                else "Corriger référentiel fournisseur"
                if blocked_reason
                else "Surveiller"
            ),
            "estimated_delivery_date": (
                (utcnow() + timedelta(days=supplier.lead_time_days)).date().isoformat()
                if supplier and supplier.lead_time_days
                else None
            ),
        })

    priority_rank = {"CRITICAL": 0, "URGENT": 1, "TO_PLAN": 2, "COVERED": 3}
    needs.sort(key=lambda item: (priority_rank.get(item["priority"], 9), item["supplier"] or "ZZZ", item["product_name"]))

    groups_by_supplier: dict[str, dict] = {}
    for need in needs:
        key = need["supplier"] or "Sans fournisseur"
        group = groups_by_supplier.setdefault(key, {
            "supplier": need["supplier"],
            "supplier_id": need["supplier_id"],
            "supplier_status": need["supplier_status"],
            "is_orderable": bool(need["supplier"]) and need["is_orderable"],
            "blocked_reason": need["blocked_reason"],
            "lines_count": 0,
            "critical_count": 0,
            "urgent_count": 0,
            "to_plan_count": 0,
            "covered_count": 0,
            "incoming_purchase_quantity": 0.0,
            "open_purchase_request_quantity": 0.0,
            "suggested_quantity": 0.0,
            "suggested_lines": [],
        })
        group["lines_count"] += 1
        if need["priority"] == "CRITICAL":
            group["critical_count"] += 1
        elif need["priority"] == "URGENT":
            group["urgent_count"] += 1
        elif need["priority"] == "TO_PLAN":
            group["to_plan_count"] += 1
        else:
            group["covered_count"] += 1
        group["incoming_purchase_quantity"] += need["incoming_purchase_quantity"]
        group["open_purchase_request_quantity"] += need["open_purchase_request_quantity"]
        group["suggested_quantity"] += need["suggested_quantity"]
        if not need["is_orderable"]:
            group["is_orderable"] = False
            group["blocked_reason"] = group["blocked_reason"] or need["blocked_reason"]
        group["suggested_lines"].append({
            "variant_id": need["variant_id"],
            "reference": need["reference"],
            "product_name": need["product_name"],
            "suggested_quantity": need["suggested_quantity"],
            "incoming_purchase_quantity": need["incoming_purchase_quantity"],
            "open_purchase_request_quantity": need["open_purchase_request_quantity"],
            "net_need_quantity": need["net_need_quantity"],
            "priority": need["priority"],
            "origins": need["origins"],
        })

    return {
        "summary": {
            "needs_count": len(needs),
            "critical_count": sum(1 for need in needs if need["priority"] == "CRITICAL"),
            "urgent_count": sum(1 for need in needs if need["priority"] == "URGENT"),
            "to_plan_count": sum(1 for need in needs if need["priority"] == "TO_PLAN"),
            "covered_count": sum(1 for need in needs if need["priority"] == "COVERED"),
            "blocked_count": sum(1 for need in needs if not need["is_orderable"]),
            "suppliers_count": len(groups_by_supplier),
            "suggested_quantity": sum(float(need["suggested_quantity"] or 0) for need in needs),
            "incoming_purchase_quantity": sum(float(need["incoming_purchase_quantity"] or 0) for need in needs),
            "open_purchase_request_quantity": sum(float(need["open_purchase_request_quantity"] or 0) for need in needs),
        },
        "needs": needs,
        "groups": list(groups_by_supplier.values()),
    }

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
            "is_late": metrics["is_late"],
            "late_days": metrics["late_days"],
        })
    return result

@router.get("/requests")
def get_purchase_requests(db: Session = Depends(get_db)):
    requests = (
        db.query(models.PurchaseRequest)
        .order_by(models.PurchaseRequest.created_at.desc(), models.PurchaseRequest.id.desc())
        .all()
    )
    return [_serialize_purchase_request(request) for request in requests]

@router.post("/requests")
def create_purchase_request(
    data: PurchaseRequestCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    security.assert_permission(db, current_user, "purchases.request")
    if not data.lines:
        raise HTTPException(status_code=400, detail="La demande d'achat doit contenir au moins une ligne.")

    requested_variant_ids = {
        line.variant_id
        for line in data.lines
        if line.variant_id and float(line.quantity or 0) > 0
    }
    if requested_variant_ids:
        duplicate_lines = (
            db.query(models.PurchaseRequestLine)
            .join(models.PurchaseRequest, models.PurchaseRequestLine.request_id == models.PurchaseRequest.id)
            .filter(
                models.PurchaseRequest.status.in_([
                    models.PurchaseRequestStatus.PENDING_APPROVAL,
                    models.PurchaseRequestStatus.APPROVED,
                ]),
                models.PurchaseRequestLine.variant_id.in_(requested_variant_ids),
            )
            .all()
        )
        if duplicate_lines:
            refs = []
            for duplicate in duplicate_lines[:8]:
                refs.append(
                    duplicate.variant.reference
                    if duplicate.variant
                    else f"variante #{duplicate.variant_id}"
                )
            raise HTTPException(
                status_code=409,
                detail="Demande d'achat déjà ouverte pour: " + ", ".join(refs),
            )

    total = _purchase_payload_total(data)
    request = models.PurchaseRequest(
        reference=_purchase_request_reference(db),
        supplier=data.supplier,
        expected_date=data.expected_date,
        status=models.PurchaseRequestStatus.PENDING_APPROVAL,
        total_amount=total,
        global_discount_percent=max(0, min(float(data.global_discount_percent or 0), 100)),
        sensitivity_reason=data.sensitivity_reason or ("Montant sensible" if total >= 1000 else "Validation achat requise"),
        notes=data.notes,
        requested_by=current_user.get("sub", "unknown"),
    )
    db.add(request)
    db.flush()

    created_lines = 0
    for line in data.lines:
        quantity = max(float(line.quantity or 0), 0)
        if quantity <= 0:
            continue
        db.add(models.PurchaseRequestLine(
            request_id=request.id,
            variant_id=line.variant_id,
            quantity=quantity,
            unit_price=max(float(line.unit_price or 0), 0),
            discount_percent=max(0, min(float(line.discount_percent or 0), 100)),
            need_priority=line.need_priority,
            need_reason=line.need_reason,
        ))
        created_lines += 1

    if created_lines == 0:
        raise HTTPException(status_code=400, detail="Aucune quantité positive dans la demande d'achat.")

    db.commit()
    db.refresh(request)
    return _serialize_purchase_request(request)

@router.post("/requests/{request_id}/approve")
def approve_purchase_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    security.assert_permission(db, current_user, "purchases.approve")
    request = db.query(models.PurchaseRequest).filter(models.PurchaseRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Demande d'achat introuvable.")
    if request.status != models.PurchaseRequestStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail="Seules les demandes en attente peuvent être validées.")
    request.status = models.PurchaseRequestStatus.APPROVED
    request.approved_by = current_user.get("sub", "unknown")
    request.approved_at = utcnow()
    db.commit()
    db.refresh(request)
    return _serialize_purchase_request(request)

@router.post("/requests/{request_id}/reject")
def reject_purchase_request(
    request_id: int,
    data: PurchaseRequestRejectInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    security.assert_permission(db, current_user, "purchases.approve")
    reason = (data.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Le motif de refus est obligatoire.")
    request = db.query(models.PurchaseRequest).filter(models.PurchaseRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Demande d'achat introuvable.")
    if request.status != models.PurchaseRequestStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail="Seules les demandes en attente peuvent être refusées.")
    request.status = models.PurchaseRequestStatus.REJECTED
    request.rejected_by = current_user.get("sub", "unknown")
    request.rejected_at = utcnow()
    request.rejection_reason = reason
    db.commit()
    db.refresh(request)
    return _serialize_purchase_request(request)

@router.post("/requests/{request_id}/convert")
def convert_purchase_request_to_order(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    security.assert_permission(db, current_user, "purchases.order")
    request = db.query(models.PurchaseRequest).filter(models.PurchaseRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Demande d'achat introuvable.")
    if request.status != models.PurchaseRequestStatus.APPROVED:
        raise HTTPException(status_code=400, detail="La demande doit être validée avant création du bon fournisseur.")
    if request.purchase_order_id:
        raise HTTPException(status_code=400, detail="Cette demande a déjà été convertie en bon fournisseur.")

    po_data = PurchaseOrderCreate(
        supplier=request.supplier,
        expected_date=request.expected_date,
        global_discount_percent=float(request.global_discount_percent or 0),
        notes=f"Créé depuis {request.reference}. {request.notes or ''}".strip(),
        lines=[
            PurchaseOrderLineInput(
                variant_id=line.variant_id,
                quantity=float(line.quantity or 0),
                unit_price=float(line.unit_price or 0),
                discount_percent=float(line.discount_percent or 0),
            )
            for line in request.lines
        ],
    )
    po = _create_purchase_order_from_data(po_data, db, current_user.get("sub", "unknown"))
    request.status = models.PurchaseRequestStatus.CONVERTED
    request.converted_by = current_user.get("sub", "unknown")
    request.converted_at = utcnow()
    request.purchase_order_id = po.id
    db.commit()
    db.refresh(request)
    db.refresh(po)
    return {"request": _serialize_purchase_request(request), "purchase_order": {"id": po.id, "reference": po.reference}}

@router.post("/")
def create_purchase_order(
    data: PurchaseOrderCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    security.assert_permission(db, current_user, "purchases.order")
    po = _create_purchase_order_from_data(data, db, current_user.get("sub", "unknown"))
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
        "is_late": metrics["is_late"],
        "late_days": metrics["late_days"],
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

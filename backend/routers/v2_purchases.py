from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from io import BytesIO
from pydantic import BaseModel
from typing import List, Optional
import uuid
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from backend.database import get_db
from backend import models
from backend.core import security, uploads
from backend.core.events import _send_smtp_email
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
    delivery_note_reference: Optional[str] = None
    notes: Optional[str] = None

class SupplierInvoiceLineInput(BaseModel):
    purchase_order_line_id: int
    quantity: float

class SupplierInvoiceCreate(BaseModel):
    supplier_reference: Optional[str] = None
    issue_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    notes: Optional[str] = None
    lines: List[SupplierInvoiceLineInput]

class SupplierPaymentCreate(BaseModel):
    amount: float
    method: str = "TRANSFER"
    reference: Optional[str] = None
    notes: Optional[str] = None
    payment_date: Optional[datetime] = None

class SupplierDisputeCreate(BaseModel):
    supplier: str
    purchase_order_id: Optional[int] = None
    supplier_invoice_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    category: str = "OTHER"
    severity: str = "MEDIUM"
    expected_quantity: Optional[float] = None
    received_quantity: Optional[float] = None
    expected_unit_price: Optional[float] = None
    invoiced_unit_price: Optional[float] = None
    expected_action: Optional[str] = None
    due_date: Optional[datetime] = None
    blocks_receipt: bool = False
    blocks_payment: bool = False
    impact_summary: Optional[str] = None

class SupplierDisputeResolveInput(BaseModel):
    resolution_notes: str

class SupplierReminderCreate(BaseModel):
    channel: str = "email"
    recipient: Optional[str] = None
    cc: Optional[str] = None
    subject: Optional[str] = None
    message: Optional[str] = None
    include_pdf: bool = True
    send_email: bool = True

PURCHASE_DIRECT_ORDER_LIMIT = 1000.0

def _supplier_invoice_reference(db: Session) -> str:
    # Format: FF-YYYY-XXXX — séquence transactionnelle inaltérable (NF525)
    return next_number(db, "supplier_invoice")

def _purchase_request_reference(db: Session) -> str:
    return next_number(db, "purchase_request")

def _supplier_dispute_reference(db: Session) -> str:
    return next_number(db, "supplier_dispute")

def _serialize_supplier_dispute_attachment(attachment: models.SupplierDisputeAttachment) -> dict:
    return {
        "id": attachment.id,
        "dispute_id": attachment.dispute_id,
        "original_filename": attachment.original_filename,
        "stored_filename": attachment.stored_filename,
        "content_type": attachment.content_type,
        "file_size": attachment.file_size or 0,
        "uploaded_by": attachment.uploaded_by,
        "uploaded_at": attachment.uploaded_at,
    }

def _serialize_supplier_dispute_event(event: models.SupplierDisputeEvent) -> dict:
    return {
        "id": event.id,
        "dispute_id": event.dispute_id,
        "event_type": event.event_type,
        "message": event.message,
        "actor": event.actor,
        "created_at": event.created_at,
    }

def _record_supplier_dispute_event(
    db: Session,
    dispute_id: int,
    event_type: str,
    message: str,
    actor: str,
) -> models.SupplierDisputeEvent:
    event = models.SupplierDisputeEvent(
        dispute_id=dispute_id,
        event_type=event_type,
        message=message,
        actor=actor,
    )
    db.add(event)
    return event

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

def _purchase_approval_reason(data: PurchaseOrderCreate, db: Session) -> Optional[str]:
    total = _purchase_payload_total(data)
    supplier_name = (data.supplier or "").strip()
    supplier = (
        db.query(models.Supplier)
        .filter(models.Supplier.name == supplier_name)
        .first()
        if supplier_name
        else None
    )
    if supplier and supplier.supplier_status == "BLOCKED":
        return "Fournisseur bloqué: demande achat impossible sans levée du blocage."
    if supplier and supplier.supplier_status == "TO_QUALIFY":
        return "Fournisseur à qualifier: une demande d'achat doit être validée avant engagement."
    if total >= PURCHASE_DIRECT_ORDER_LIMIT:
        return f"Montant achat sensible ({total:.2f} €): validation achat obligatoire."
    priority_lines = [
        line.need_priority
        for line in data.lines
        if str(line.need_priority or "").upper() in {"CRITICAL", "URGENT"}
    ]
    if priority_lines:
        return "Besoin critique/urgent: validation achat obligatoire avant bon fournisseur."
    return None

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
    paid_amount = sum(float(payment.amount or 0) for payment in invoice.payments)
    total_amount = float(invoice.total_amount or 0)
    remaining_amount = max(total_amount - paid_amount, 0.0)
    return {
        "id": invoice.id,
        "reference": invoice.reference,
        "supplier_reference": invoice.supplier_reference,
        "issue_date": invoice.issue_date,
        "due_date": invoice.due_date,
        "status": invoice.status,
        "subtotal": float(invoice.subtotal or 0),
        "discount_amount": float(invoice.discount_amount or 0),
        "total_amount": total_amount,
        "paid_amount": paid_amount,
        "remaining_amount": remaining_amount,
        "notes": invoice.notes,
        "payments": [
            {
                "id": payment.id,
                "amount": float(payment.amount or 0),
                "method": payment.method,
                "reference": payment.reference,
                "notes": payment.notes,
                "payment_date": payment.payment_date,
                "created_by": payment.created_by,
                "created_at": payment.created_at,
            }
            for payment in invoice.payments
        ],
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

def _serialize_supplier_dispute(dispute: models.SupplierDispute) -> dict:
    return {
        "id": dispute.id,
        "reference": dispute.reference,
        "supplier": dispute.supplier,
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
        "closed_by": dispute.closed_by,
        "closed_at": dispute.closed_at,
        "resolution_notes": dispute.resolution_notes,
        "attachments": [
            _serialize_supplier_dispute_attachment(attachment)
            for attachment in sorted(dispute.attachments or [], key=lambda item: (item.uploaded_at or datetime.min, item.id), reverse=True)
        ],
        "events": [
            _serialize_supplier_dispute_event(event)
            for event in sorted(dispute.events or [], key=lambda item: (item.created_at or datetime.min, item.id), reverse=True)
        ],
    }

def _serialize_supplier_reminder(reminder: models.SupplierReminder) -> dict:
    return {
        "id": reminder.id,
        "purchase_order_id": reminder.purchase_order_id,
        "supplier": reminder.supplier,
        "channel": reminder.channel,
        "recipient": reminder.recipient,
        "cc": reminder.cc,
        "subject": reminder.subject,
        "message": reminder.message,
        "status": reminder.status,
        "error_message": reminder.error_message,
        "include_pdf": reminder.include_pdf,
        "sent_at": reminder.sent_at,
        "created_by": reminder.created_by,
        "created_at": reminder.created_at,
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

def _open_blocking_disputes(db: Session, po_id: int, block_field: str) -> List[models.SupplierDispute]:
    if block_field not in {"blocks_receipt", "blocks_payment"}:
        return []
    return (
        db.query(models.SupplierDispute)
        .filter(
            models.SupplierDispute.purchase_order_id == po_id,
            models.SupplierDispute.status.in_(["OPEN", "IN_PROGRESS"]),
            getattr(models.SupplierDispute, block_field) == True,  # noqa: E712
        )
        .order_by(models.SupplierDispute.created_at.desc(), models.SupplierDispute.id.desc())
        .all()
    )

def _supplier_invoice_remaining_amount(invoice: models.SupplierInvoice) -> float:
    total_amount = float(invoice.total_amount or 0)
    paid_amount = sum(float(payment.amount or 0) for payment in invoice.payments)
    return max(total_amount - paid_amount, 0.0)

def _invoice_payment_blockers(db: Session, invoice: models.SupplierInvoice) -> List[models.SupplierDispute]:
    filters = [
        models.SupplierDispute.status.in_(["OPEN", "IN_PROGRESS"]),
        models.SupplierDispute.blocks_payment == True,  # noqa: E712
    ]
    if invoice.purchase_order_id:
        filters.append(models.SupplierDispute.purchase_order_id == invoice.purchase_order_id)
    else:
        filters.append(models.SupplierDispute.supplier_invoice_id == invoice.id)
    return (
        db.query(models.SupplierDispute)
        .filter(*filters)
        .order_by(models.SupplierDispute.created_at.desc(), models.SupplierDispute.id.desc())
        .all()
    )

def _supplier_invoice_payment_status(db: Session, invoice: models.SupplierInvoice) -> dict:
    remaining_amount = _supplier_invoice_remaining_amount(invoice)
    blockers = _invoice_payment_blockers(db, invoice)
    today = utcnow().date()
    due_date = invoice.due_date.date() if invoice.due_date else None
    overdue_days = max((today - due_date).days, 0) if due_date else 0
    return {
        "remaining_amount": remaining_amount,
        "is_payable": remaining_amount > 0 and not blockers and invoice.status != "CANCELLED",
        "is_blocked": bool(blockers),
        "blocker_references": [dispute.reference for dispute in blockers],
        "is_overdue": overdue_days > 0 and remaining_amount > 0,
        "overdue_days": overdue_days,
    }

def _draw_pdf_text(pdf: canvas.Canvas, x: float, y: float, text: str, size: int = 9, bold: bool = False) -> None:
    pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    pdf.drawString(x, y, str(text or ""))

def _generate_purchase_order_pdf(po: models.PurchaseOrder, db: Session) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 18 * mm
    y = height - margin
    metrics = _purchase_order_metrics(po, db)

    def new_page():
        nonlocal y
        pdf.showPage()
        y = height - margin

    def ensure_space(required: float):
        if y - required < margin:
            new_page()

    pdf.setFillColor(colors.HexColor("#0f172a"))
    pdf.rect(0, height - 42 * mm, width, 42 * mm, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    _draw_pdf_text(pdf, margin, y, "MMG MENUISERIES", 16, True)
    _draw_pdf_text(pdf, margin, y - 8 * mm, "Bon fournisseur", 11)
    _draw_pdf_text(pdf, width - 76 * mm, y, po.reference, 16, True)
    _draw_pdf_text(pdf, width - 76 * mm, y - 8 * mm, f"Statut: {po.status}", 9)
    y -= 54 * mm

    pdf.setFillColor(colors.HexColor("#0f172a"))
    _draw_pdf_text(pdf, margin, y, "Fournisseur", 10, True)
    _draw_pdf_text(pdf, margin, y - 7 * mm, po.supplier, 13, True)
    _draw_pdf_text(pdf, margin, y - 15 * mm, f"Commande: {po.order_date.strftime('%d/%m/%Y') if po.order_date else '-'}", 9)
    _draw_pdf_text(pdf, margin, y - 22 * mm, f"Livraison prévue: {po.expected_date.strftime('%d/%m/%Y') if po.expected_date else 'Non renseignée'}", 9)
    _draw_pdf_text(pdf, width - 78 * mm, y, "Suivi réception", 10, True)
    _draw_pdf_text(pdf, width - 78 * mm, y - 8 * mm, f"Commandé: {metrics['quantity_ordered']:.2f}", 9)
    _draw_pdf_text(pdf, width - 78 * mm, y - 15 * mm, f"Reçu: {metrics['quantity_received']:.2f}", 9)
    _draw_pdf_text(pdf, width - 78 * mm, y - 22 * mm, f"Reste: {metrics['quantity_remaining']:.2f}", 9)
    y -= 36 * mm

    pdf.setFillColor(colors.HexColor("#f8fafc"))
    pdf.rect(margin, y - 8 * mm, width - 2 * margin, 10 * mm, fill=1, stroke=0)
    pdf.setFillColor(colors.HexColor("#475569"))
    headers = [("Référence", 0), ("Désignation", 35), ("Qté", 103), ("Reçu", 119), ("PU HT", 137), ("Remise", 156), ("Total HT", 176)]
    for label, offset in headers:
        _draw_pdf_text(pdf, margin + offset * mm, y - 4.5 * mm, label, 7, True)
    y -= 12 * mm

    pdf.setFillColor(colors.HexColor("#0f172a"))
    for line in po.lines:
        ensure_space(16 * mm)
        variant_ref = line.variant.reference if line.variant else "-"
        product_name = line.variant.product.name if line.variant and line.variant.product else "Article"
        line_total = _line_total(float(line.quantity or 0), float(line.unit_price or 0), float(line.discount_percent or 0))
        _draw_pdf_text(pdf, margin, y, variant_ref[:24], 8, True)
        _draw_pdf_text(pdf, margin + 35 * mm, y, product_name[:54], 8)
        _draw_pdf_text(pdf, margin + 103 * mm, y, f"{float(line.quantity or 0):.2f}", 8)
        _draw_pdf_text(pdf, margin + 119 * mm, y, f"{float(line.quantity_received or 0):.2f}", 8)
        _draw_pdf_text(pdf, margin + 137 * mm, y, f"{float(line.unit_price or 0):.2f}", 8)
        _draw_pdf_text(pdf, margin + 156 * mm, y, f"{float(line.discount_percent or 0):.1f}%", 8)
        _draw_pdf_text(pdf, margin + 176 * mm, y, f"{line_total:.2f}", 8, True)
        pdf.setStrokeColor(colors.HexColor("#e2e8f0"))
        pdf.line(margin, y - 3 * mm, width - margin, y - 3 * mm)
        y -= 9 * mm

    ensure_space(34 * mm)
    y -= 6 * mm
    pdf.setFillColor(colors.HexColor("#0f172a"))
    _draw_pdf_text(pdf, width - 78 * mm, y, f"Total HT: {float(po.total_amount or 0):.2f} EUR", 13, True)
    y -= 11 * mm
    _draw_pdf_text(pdf, margin, y, "Conditions / notes", 10, True)
    y -= 7 * mm
    notes = po.notes or "Bon fournisseur généré depuis MMG."
    for chunk in [notes[i:i + 95] for i in range(0, len(notes), 95)][:6]:
        ensure_space(7 * mm)
        _draw_pdf_text(pdf, margin, y, chunk, 8)
        y -= 6 * mm

    pdf.setFillColor(colors.HexColor("#64748b"))
    _draw_pdf_text(pdf, margin, margin - 4 * mm, "Document achat généré par MMG - rapprocher les factures uniquement sur quantités reçues.", 7)
    pdf.save()
    return buffer.getvalue()

def _line_match_status(quantity_received: float, quantity_invoiced: float) -> str:
    if quantity_received <= 0:
        return "NO_RECEIPT"
    if quantity_invoiced <= 0:
        return "TO_INVOICE"
    if quantity_invoiced < quantity_received:
        return "PARTIAL_MATCH"
    return "MATCHED"

_VAGUE_LOCATION_WORDS = {
    "divers",
    "stock",
    "test",
    "zone",
    "autre",
    "temp",
    "temporary",
    "vrac",
    "inconnu",
    "unknown",
}


def _location_full_name(db: Session, location: models.StockLocation) -> str:
    names = []
    current = location
    seen = set()
    while current and current.id not in seen:
        seen.add(current.id)
        names.append(current.name or "")
        current = db.query(models.StockLocation).filter_by(id=current.parent_id).first() if current.parent_id else None
    return " > ".join(reversed([name for name in names if name]))


def _location_role(db: Session, location: models.StockLocation) -> str:
    label = f"{location.name or ''} {_location_full_name(db, location)}".lower()
    if location.usage == "production" or "atelier" in label or "préparation" in label or "preparation" in label:
        return "Zone atelier"
    if "casier" in label or "case" in label or "bac" in label:
        return "Casier final"
    if "rack" in label or "travée" in label or "travee" in label or "étag" in label or "etag" in label:
        return "Rack"
    last_segment = (location.name or "").split("/")[-1].strip().lower()
    if len(last_segment) >= 2 and last_segment[0].isalpha() and last_segment[1:].isdigit():
        return "Casier final"
    return "Zone parent" if location.parent_id else "Magasin"


def _assert_receipt_target_exploitable(db: Session, location_id: int) -> models.StockLocation:
    location = db.query(models.StockLocation).filter_by(id=location_id, is_active=True).first()
    if not location:
        raise HTTPException(status_code=400, detail="Emplacement de réception introuvable ou archivé.")
    if location.usage not in {"internal", "production"}:
        raise HTTPException(status_code=400, detail="La réception fournisseur doit cibler un emplacement physique interne.")

    name = (location.name or "").strip().lower()
    first_word = name.split(" ", 1)[0] if name else ""
    compact_slot = len(name) >= 2 and name[0].isalpha() and name[1:].isdigit()
    role = _location_role(db, location)
    issues = []
    if not name:
        issues.append("nom absent")
    if name and len(name) < 3 and not compact_slot:
        issues.append("nom trop court")
    if name in _VAGUE_LOCATION_WORDS or first_word in (_VAGUE_LOCATION_WORDS - {"zone"}):
        issues.append("nom trop vague")
    if role in {"Magasin", "Zone parent"}:
        issues.append("rack, casier ou zone atelier à préciser")

    if issues:
        detail = ", ".join(issues)
        raise HTTPException(
            status_code=400,
            detail=f"Emplacement non exploitable pour réception fournisseur: {detail}.",
        )
    return location

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
            "open_disputes": db.query(models.SupplierDispute).filter(
                models.SupplierDispute.purchase_order_id == po.id,
                models.SupplierDispute.status.in_(["OPEN", "IN_PROGRESS"]),
            ).count(),
        })
    return result

@router.get("/dashboard")
def get_purchase_dashboard(db: Session = Depends(get_db)):
    pos = db.query(models.PurchaseOrder).order_by(models.PurchaseOrder.order_date.desc()).all()
    requests = db.query(models.PurchaseRequest).all()
    supplier_invoices = (
        db.query(models.SupplierInvoice)
        .filter(models.SupplierInvoice.status != "CANCELLED")
        .order_by(models.SupplierInvoice.due_date.asc().nullslast(), models.SupplierInvoice.issue_date.desc())
        .all()
    )
    open_disputes = db.query(models.SupplierDispute).filter(
        models.SupplierDispute.status.in_(["OPEN", "IN_PROGRESS"])
    ).all()
    today = utcnow().date()

    summary = {
        "open_orders": 0,
        "to_receive": 0,
        "late_orders": 0,
        "to_invoice": 0,
        "supplier_invoices_to_pay": 0,
        "supplier_invoices_overdue": 0,
        "supplier_invoices_blocked": 0,
        "open_disputes": len(open_disputes),
        "pending_requests": sum(1 for request in requests if request.status == models.PurchaseRequestStatus.PENDING_APPROVAL),
        "approved_requests": sum(1 for request in requests if request.status == models.PurchaseRequestStatus.APPROVED),
        "amount_committed": 0.0,
        "amount_to_pay": 0.0,
        "amount_overdue": 0.0,
        "amount_blocked": 0.0,
        "cash_out_7_days": 0.0,
        "cash_out_30_days": 0.0,
        "cash_out_60_days": 0.0,
    }
    actions = []
    payment_schedule = []

    for po in pos:
        metrics = _purchase_order_metrics(po, db)
        is_closed = po.status in [models.PurchaseOrderStatus.CANCELLED, models.PurchaseOrderStatus.RECEIVED]
        if not is_closed:
            summary["open_orders"] += 1
            summary["amount_committed"] += float(po.total_amount or 0)
        if metrics["quantity_remaining"] > 0:
            summary["to_receive"] += 1
        if metrics["is_late"]:
            summary["late_orders"] += 1
        if metrics["quantity_invoiceable"] > 0:
            summary["to_invoice"] += 1

        if metrics["is_late"] or metrics["quantity_invoiceable"] > 0 or metrics["quantity_remaining"] > 0:
            actions.append({
                "type": "LATE" if metrics["is_late"] else "INVOICE" if metrics["quantity_invoiceable"] > 0 else "RECEIPT",
                "purchase_order_id": po.id,
                "reference": po.reference,
                "supplier": po.supplier,
                "label": metrics["next_action"],
                "late_days": metrics["late_days"],
                "quantity_remaining": metrics["quantity_remaining"],
                "quantity_invoiceable": metrics["quantity_invoiceable"],
                "total_amount": po.total_amount,
            })

    for request in requests:
        if request.status in [models.PurchaseRequestStatus.PENDING_APPROVAL, models.PurchaseRequestStatus.APPROVED]:
            actions.append({
                "type": "REQUEST",
                "purchase_request_id": request.id,
                "reference": request.reference,
                "supplier": request.supplier,
                "label": "Valider demande achat" if request.status == models.PurchaseRequestStatus.PENDING_APPROVAL else "Créer bon fournisseur",
                "total_amount": request.total_amount,
                "status": request.status,
            })

    for dispute in open_disputes:
        actions.append({
            "type": "DISPUTE",
            "dispute_id": dispute.id,
            "purchase_order_id": dispute.purchase_order_id,
            "reference": dispute.reference,
            "supplier": dispute.supplier,
            "label": dispute.title,
            "severity": dispute.severity,
            "status": dispute.status,
        })

    for invoice in supplier_invoices:
        payment_status = _supplier_invoice_payment_status(db, invoice)
        remaining_amount = payment_status["remaining_amount"]
        if remaining_amount <= 0:
            continue

        summary["supplier_invoices_to_pay"] += 1
        summary["amount_to_pay"] += remaining_amount

        due_date = invoice.due_date.date() if invoice.due_date else None
        days_until_due = (due_date - today).days if due_date else None
        if payment_status["is_overdue"]:
            summary["supplier_invoices_overdue"] += 1
            summary["amount_overdue"] += remaining_amount
        if payment_status["is_blocked"]:
            summary["supplier_invoices_blocked"] += 1
            summary["amount_blocked"] += remaining_amount
        if days_until_due is not None and days_until_due <= 7:
            summary["cash_out_7_days"] += remaining_amount
        if days_until_due is not None and days_until_due <= 30:
            summary["cash_out_30_days"] += remaining_amount
        if days_until_due is not None and days_until_due <= 60:
            summary["cash_out_60_days"] += remaining_amount

        item = {
            "invoice_id": invoice.id,
            "purchase_order_id": invoice.purchase_order_id,
            "reference": invoice.reference,
            "supplier_reference": invoice.supplier_reference,
            "supplier": invoice.supplier,
            "due_date": invoice.due_date,
            "remaining_amount": remaining_amount,
            "total_amount": float(invoice.total_amount or 0),
            "status": invoice.status,
            "is_overdue": payment_status["is_overdue"],
            "overdue_days": payment_status["overdue_days"],
            "is_blocked": payment_status["is_blocked"],
            "blocker_references": payment_status["blocker_references"],
            "days_until_due": days_until_due,
        }
        payment_schedule.append(item)
        if payment_status["is_overdue"] or payment_status["is_blocked"]:
            actions.append({
                "type": "PAYMENT_BLOCKED" if payment_status["is_blocked"] else "PAYMENT_DUE",
                "invoice_id": invoice.id,
                "purchase_order_id": invoice.purchase_order_id,
                "reference": invoice.reference,
                "supplier": invoice.supplier,
                "label": "Paiement bloqué par litige" if payment_status["is_blocked"] else "Facture fournisseur en retard de paiement",
                "remaining_amount": remaining_amount,
                "overdue_days": payment_status["overdue_days"],
                "blocker_references": payment_status["blocker_references"],
            })

    payment_schedule.sort(key=lambda item: (
        item["is_blocked"] is False,
        item["days_until_due"] if item["days_until_due"] is not None else 9999,
        item["supplier"] or "",
    ))
    priority = {"LATE": 0, "PAYMENT_BLOCKED": 1, "PAYMENT_DUE": 2, "DISPUTE": 3, "INVOICE": 4, "REQUEST": 5, "RECEIPT": 6}
    actions.sort(key=lambda item: (priority.get(item["type"], 9), -int(item.get("late_days") or 0), item.get("supplier") or ""))
    return {
        "summary": summary,
        "actions": actions[:20],
        "payment_schedule": payment_schedule[:20],
        "cash_out_forecast": [
            {"label": "7 jours", "days": 7, "amount": summary["cash_out_7_days"]},
            {"label": "30 jours", "days": 30, "amount": summary["cash_out_30_days"]},
            {"label": "60 jours", "days": 60, "amount": summary["cash_out_60_days"]},
        ],
    }

@router.get("/disputes")
def get_supplier_disputes(db: Session = Depends(get_db)):
    disputes = (
        db.query(models.SupplierDispute)
        .order_by(models.SupplierDispute.created_at.desc(), models.SupplierDispute.id.desc())
        .all()
    )
    return [_serialize_supplier_dispute(dispute) for dispute in disputes]

@router.post("/disputes")
def create_supplier_dispute(
    data: SupplierDisputeCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    security.assert_permission(db, current_user, "purchases.receive")
    supplier = (data.supplier or "").strip()
    title = (data.title or "").strip()
    if not supplier:
        raise HTTPException(status_code=400, detail="Le fournisseur est obligatoire.")
    if not title:
        raise HTTPException(status_code=400, detail="Le titre du litige est obligatoire.")
    category = (data.category or "OTHER").upper()
    severity = (data.severity or "MEDIUM").upper()
    expected_action = (data.expected_action or "").strip().upper() or None
    if category not in {"DELAY", "QUANTITY", "QUALITY", "PRICE", "DOCUMENT", "OTHER"}:
        raise HTTPException(status_code=400, detail="Catégorie de litige invalide.")
    if severity not in {"LOW", "MEDIUM", "HIGH", "BLOCKING"}:
        raise HTTPException(status_code=400, detail="Sévérité de litige invalide.")
    if expected_action and expected_action not in {"REDELIVER", "CREDIT_NOTE", "REPLACE", "PRICE_CORRECTION", "INFO", "OTHER"}:
        raise HTTPException(status_code=400, detail="Action attendue invalide.")

    if data.purchase_order_id:
        po = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id == data.purchase_order_id).first()
        if not po:
            raise HTTPException(status_code=404, detail="Bon fournisseur introuvable.")
        if po.supplier != supplier:
            raise HTTPException(status_code=400, detail="Le litige ne correspond pas au fournisseur du bon.")

    if data.supplier_invoice_id:
        invoice = db.query(models.SupplierInvoice).filter(models.SupplierInvoice.id == data.supplier_invoice_id).first()
        if not invoice:
            raise HTTPException(status_code=404, detail="Facture fournisseur introuvable.")
        if invoice.supplier != supplier:
            raise HTTPException(status_code=400, detail="Le litige ne correspond pas au fournisseur de la facture.")

    dispute = models.SupplierDispute(
        reference=_supplier_dispute_reference(db),
        supplier=supplier,
        purchase_order_id=data.purchase_order_id,
        supplier_invoice_id=data.supplier_invoice_id,
        title=title,
        description=data.description,
        category=category,
        severity=severity,
        expected_quantity=data.expected_quantity,
        received_quantity=data.received_quantity,
        expected_unit_price=data.expected_unit_price,
        invoiced_unit_price=data.invoiced_unit_price,
        expected_action=expected_action,
        due_date=data.due_date,
        blocks_receipt=bool(data.blocks_receipt),
        blocks_payment=bool(data.blocks_payment),
        impact_summary=data.impact_summary,
        status="OPEN",
        created_by=current_user.get("sub", "unknown"),
    )
    db.add(dispute)
    db.flush()
    _record_supplier_dispute_event(
        db,
        dispute.id,
        "CREATED",
        f"Litige ouvert: {title}",
        current_user.get("sub", "unknown"),
    )
    db.commit()
    db.refresh(dispute)
    return _serialize_supplier_dispute(dispute)

@router.get("/disputes/{dispute_id}/attachments")
def get_supplier_dispute_attachments(
    dispute_id: int,
    db: Session = Depends(get_db),
):
    dispute = db.query(models.SupplierDispute).filter(models.SupplierDispute.id == dispute_id).first()
    if not dispute:
        raise HTTPException(status_code=404, detail="Litige fournisseur introuvable.")
    return [_serialize_supplier_dispute_attachment(attachment) for attachment in dispute.attachments]

@router.post("/disputes/{dispute_id}/attachments")
async def upload_supplier_dispute_attachment(
    dispute_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    security.assert_permission(db, current_user, "purchases.receive")
    dispute = db.query(models.SupplierDispute).filter(models.SupplierDispute.id == dispute_id).first()
    if not dispute:
        raise HTTPException(status_code=404, detail="Litige fournisseur introuvable.")
    if dispute.status == "RESOLVED":
        raise HTTPException(status_code=400, detail="Impossible d'ajouter une preuve sur un litige résolu.")

    file_path = await uploads.save_upload_file(
        file,
        os.path.join("uploads", "supplier_disputes", str(dispute.id)),
        extra_extensions={".txt"},
        prefix=f"litige_{dispute.id}_",
    )
    attachment = models.SupplierDisputeAttachment(
        dispute_id=dispute.id,
        original_filename=os.path.basename(file.filename or "preuve"),
        stored_filename=os.path.basename(file_path),
        content_type=file.content_type,
        file_path=file_path.replace(os.sep, "/"),
        file_size=os.path.getsize(file_path) if os.path.exists(file_path) else 0,
        uploaded_by=current_user.get("sub", "unknown"),
    )
    db.add(attachment)
    db.flush()
    _record_supplier_dispute_event(
        db,
        dispute.id,
        "ATTACHMENT_ADDED",
        f"Preuve ajoutée: {attachment.original_filename}",
        current_user.get("sub", "unknown"),
    )
    db.commit()
    db.refresh(dispute)
    return _serialize_supplier_dispute(dispute)

@router.get("/disputes/{dispute_id}/attachments/{attachment_id}/download")
def download_supplier_dispute_attachment(
    dispute_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
):
    attachment = (
        db.query(models.SupplierDisputeAttachment)
        .filter(
            models.SupplierDisputeAttachment.id == attachment_id,
            models.SupplierDisputeAttachment.dispute_id == dispute_id,
        )
        .first()
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="Preuve de litige introuvable.")
    if not os.path.exists(attachment.file_path):
        raise HTTPException(status_code=404, detail="Fichier de preuve introuvable.")
    filename = attachment.original_filename.replace('"', "")
    return FileResponse(
        attachment.file_path,
        media_type=attachment.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.delete("/disputes/{dispute_id}/attachments/{attachment_id}")
def delete_supplier_dispute_attachment(
    dispute_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    security.assert_permission(db, current_user, "purchases.approve")
    dispute = db.query(models.SupplierDispute).filter(models.SupplierDispute.id == dispute_id).first()
    if not dispute:
        raise HTTPException(status_code=404, detail="Litige fournisseur introuvable.")
    if dispute.status == "RESOLVED":
        raise HTTPException(status_code=400, detail="Impossible de supprimer une preuve sur un litige résolu.")
    attachment = (
        db.query(models.SupplierDisputeAttachment)
        .filter(
            models.SupplierDisputeAttachment.id == attachment_id,
            models.SupplierDisputeAttachment.dispute_id == dispute_id,
        )
        .first()
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="Preuve de litige introuvable.")
    original_filename = attachment.original_filename
    file_path = attachment.file_path
    db.delete(attachment)
    _record_supplier_dispute_event(
        db,
        dispute.id,
        "ATTACHMENT_DELETED",
        f"Preuve supprimée: {original_filename}",
        current_user.get("sub", "unknown"),
    )
    db.commit()
    if file_path and os.path.exists(file_path):
        os.remove(file_path)
    db.refresh(dispute)
    return _serialize_supplier_dispute(dispute)

@router.post("/disputes/{dispute_id}/resolve")
def resolve_supplier_dispute(
    dispute_id: int,
    data: SupplierDisputeResolveInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    security.assert_permission(db, current_user, "purchases.approve")
    notes = (data.resolution_notes or "").strip()
    if not notes:
        raise HTTPException(status_code=400, detail="Le compte rendu de résolution est obligatoire.")
    dispute = db.query(models.SupplierDispute).filter(models.SupplierDispute.id == dispute_id).first()
    if not dispute:
        raise HTTPException(status_code=404, detail="Litige fournisseur introuvable.")
    if dispute.status == "RESOLVED":
        return _serialize_supplier_dispute(dispute)
    if dispute.category in {"QUALITY", "QUANTITY"} and not dispute.attachments:
        raise HTTPException(status_code=400, detail="Une preuve est obligatoire pour résoudre un litige qualité ou quantité.")
    dispute.status = "RESOLVED"
    dispute.closed_by = current_user.get("sub", "unknown")
    dispute.closed_at = utcnow()
    dispute.resolution_notes = notes
    _record_supplier_dispute_event(
        db,
        dispute.id,
        "RESOLVED",
        f"Litige résolu: {notes}",
        current_user.get("sub", "unknown"),
    )
    db.commit()
    db.refresh(dispute)
    return _serialize_supplier_dispute(dispute)

@router.post("/disputes/{dispute_id}/start")
def start_supplier_dispute(
    dispute_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    security.assert_permission(db, current_user, "purchases.receive")
    dispute = db.query(models.SupplierDispute).filter(models.SupplierDispute.id == dispute_id).first()
    if not dispute:
        raise HTTPException(status_code=404, detail="Litige fournisseur introuvable.")
    if dispute.status == "RESOLVED":
        raise HTTPException(status_code=400, detail="Un litige résolu ne peut pas être repris.")
    dispute.status = "IN_PROGRESS"
    _record_supplier_dispute_event(
        db,
        dispute.id,
        "STARTED",
        "Litige pris en charge.",
        current_user.get("sub", "unknown"),
    )
    db.commit()
    db.refresh(dispute)
    return _serialize_supplier_dispute(dispute)

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
    if request.status == models.PurchaseRequestStatus.CONVERTED and request.purchase_order_id:
        po = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id == request.purchase_order_id).first()
        if po:
            return {"request": _serialize_purchase_request(request), "purchase_order": {"id": po.id, "reference": po.reference}}
    if request.status != models.PurchaseRequestStatus.APPROVED:
        raise HTTPException(status_code=400, detail="La demande doit être validée avant création du bon fournisseur.")
    if request.purchase_order_id:
        po = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id == request.purchase_order_id).first()
        if po:
            return {"request": _serialize_purchase_request(request), "purchase_order": {"id": po.id, "reference": po.reference}}
        raise HTTPException(status_code=409, detail="Cette demande référence un bon fournisseur introuvable.")

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
    approval_reason = _purchase_approval_reason(data, db)
    if approval_reason:
        detail = (
            f"Bon fournisseur impossible. {approval_reason}"
            if "bloqué" in approval_reason.lower()
            else f"Demande d'achat obligatoire avant bon fournisseur. {approval_reason}"
        )
        raise HTTPException(
            status_code=409,
            detail=detail,
        )
    po = _create_purchase_order_from_data(data, db, current_user.get("sub", "unknown"))
    db.commit()
    db.refresh(po)
    return {"id": po.id, "reference": po.reference}

@router.get("/{po_id}/pdf")
def download_purchase_order_pdf(po_id: int, db: Session = Depends(get_db)):
    po = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="Bon fournisseur introuvable.")
    pdf_bytes = _generate_purchase_order_pdf(po, db)
    filename = f"bon-fournisseur-{po.reference}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.post("/{po_id}/remind")
def remind_purchase_order_supplier(
    po_id: int,
    data: SupplierReminderCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    security.assert_permission(db, current_user, "purchases.receive")
    po = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="Bon fournisseur introuvable.")
    metrics = _purchase_order_metrics(po, db)
    if metrics["quantity_remaining"] <= 0:
        raise HTTPException(status_code=400, detail="Cette commande est déjà totalement réceptionnée.")
    channel = (data.channel or "email").strip().lower()
    if channel not in ["email", "phone", "portal", "other"]:
        raise HTTPException(status_code=400, detail="Canal de relance invalide.")
    supplier_record = (
        db.query(models.Supplier)
        .filter(models.Supplier.name == po.supplier)
        .first()
    )
    recipient = (data.recipient or (supplier_record.email if supplier_record else "") or "").strip()
    cc = (data.cc or os.environ.get("PURCHASES_CC_EMAIL") or "").strip() or None
    if data.send_email and channel == "email" and not recipient:
        raise HTTPException(status_code=400, detail="Aucun email fournisseur disponible pour envoyer la relance.")
    timestamp = utcnow().strftime("%Y-%m-%d %H:%M")
    message = (data.message or "").strip() or (
        f"Bonjour,\n\n"
        f"Sauf erreur de notre part, le bon fournisseur {po.reference} présente encore "
        f"{metrics['quantity_remaining']:.2f} unité(s) à réceptionner."
        + (f"\nLa livraison est en retard de {metrics['late_days']} jour(s)." if metrics["is_late"] else "")
        + "\n\nMerci de nous confirmer la date de livraison prévue.\n\nCordialement,\nMMG Menuiseries"
    )
    subject = (data.subject or "").strip() or f"Relance livraison - bon fournisseur {po.reference}"
    status = "PREPARED"
    error_message = None
    sent_at = None
    if data.send_email and channel == "email":
        text_body = message
        html_body = (
            "<html><body style=\"font-family: Arial, sans-serif; color: #1e293b;\">"
            f"<p>Bonjour,</p>"
            f"<p>Sauf erreur de notre part, le bon fournisseur <b>{po.reference}</b> présente encore "
            f"<b>{metrics['quantity_remaining']:.2f} unité(s)</b> à réceptionner.</p>"
            + (f"<p>La livraison est en retard de <b>{metrics['late_days']} jour(s)</b>.</p>" if metrics["is_late"] else "")
            + "<p>Merci de nous confirmer la date de livraison prévue.</p>"
            + "<p>Cordialement,<br/>MMG Menuiseries</p>"
            + "</body></html>"
        )
        attachments = []
        if data.include_pdf:
            attachments.append({
                "filename": f"bon-fournisseur-{po.reference}.pdf",
                "content": _generate_purchase_order_pdf(po, db),
                "subtype": "pdf",
            })
        try:
            sent = _send_smtp_email(recipient, subject, text_body, html_body, attachments=attachments, cc=cc)
            status = "SENT" if sent else "SKIPPED"
            sent_at = utcnow() if sent else None
            if not sent:
                error_message = "SMTP non configuré: relance préparée mais non envoyée."
        except Exception as exc:
            status = "FAILED"
            error_message = str(exc)

    reminder = models.SupplierReminder(
        purchase_order_id=po.id,
        supplier=po.supplier,
        channel=channel,
        recipient=recipient or None,
        cc=cc,
        subject=subject,
        message=message,
        status=status,
        error_message=error_message,
        include_pdf=bool(data.include_pdf),
        sent_at=sent_at,
        created_by=current_user.get("sub", "unknown"),
    )
    db.add(reminder)
    reminder_note = (
        f"[RELANCE FOURNISSEUR] {timestamp} par {current_user.get('sub', 'unknown')} "
        f"via {channel} vers {recipient or 'destinataire non renseigné'} ({status}): {subject}"
    )
    po.notes = f"{po.notes or ''}\n{reminder_note}".strip()
    db.commit()
    db.refresh(po)
    db.refresh(reminder)
    return {
        "status": status,
        "message": message,
        "reminder": _serialize_supplier_reminder(reminder),
        "purchase_order": {
            "id": po.id,
            "reference": po.reference,
            "supplier": po.supplier,
            "notes": po.notes,
            "quantity_remaining": metrics["quantity_remaining"],
            "late_days": metrics["late_days"],
        },
    }

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
        "disputes": [
            _serialize_supplier_dispute(dispute)
            for dispute in db.query(models.SupplierDispute)
            .filter(models.SupplierDispute.purchase_order_id == po.id)
            .order_by(models.SupplierDispute.created_at.desc(), models.SupplierDispute.id.desc())
            .all()
        ],
        "supplier_reminders": [
            _serialize_supplier_reminder(reminder)
            for reminder in db.query(models.SupplierReminder)
            .filter(models.SupplierReminder.purchase_order_id == po.id)
            .order_by(models.SupplierReminder.created_at.desc(), models.SupplierReminder.id.desc())
            .all()
        ],
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
    receipt_blockers = _open_blocking_disputes(db, po.id, "blocks_receipt")
    if receipt_blockers:
        refs = ", ".join(dispute.reference for dispute in receipt_blockers[:3])
        raise HTTPException(status_code=409, detail=f"Réception bloquée par litige fournisseur ouvert: {refs}.")
        
    if po.status == models.PurchaseOrderStatus.RECEIVED:
        raise HTTPException(status_code=400, detail="PO already fully received")
    target_location = _assert_receipt_target_exploitable(db, data.target_location_id)
        
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
            notes = [
                f"Réception fournisseur depuis {po.reference}",
                f"Rangé dans {_location_full_name(db, target_location)}",
                f"BL fournisseur: {data.delivery_note_reference.strip()}" if data.delivery_note_reference else None,
                data.notes.strip() if data.notes else None,
            ]
            try:
                InventoryService.move_stock(
                    db,
                    variant_id=line.variant_id,
                    source_location_id=supplier_loc.id,
                    dest_location_id=data.target_location_id,
                    quantity=receive_qty,
                    reference=ref_move,
                    notes=" · ".join(note for note in notes if note),
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
    security.assert_permission(db, current_user, "purchases.invoice.manage")
    po = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    payment_blockers = _open_blocking_disputes(db, po.id, "blocks_payment")
    if payment_blockers:
        refs = ", ".join(dispute.reference for dispute in payment_blockers[:3])
        raise HTTPException(status_code=409, detail=f"Rapprochement facture bloqué par litige fournisseur ouvert: {refs}.")
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

@router.post("/supplier-invoices/{invoice_id}/pay")
def pay_supplier_invoice(
    invoice_id: int,
    data: SupplierPaymentCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    security.assert_permission(db, current_user, "purchases.payments.manage")
    invoice = db.query(models.SupplierInvoice).filter(models.SupplierInvoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Facture fournisseur introuvable.")
    if invoice.status == "CANCELLED":
        raise HTTPException(status_code=400, detail="Facture fournisseur annulée.")
    if invoice.purchase_order_id:
        payment_blockers = _open_blocking_disputes(db, invoice.purchase_order_id, "blocks_payment")
        if payment_blockers:
            refs = ", ".join(dispute.reference for dispute in payment_blockers[:3])
            raise HTTPException(status_code=409, detail=f"Paiement fournisseur bloqué par litige ouvert: {refs}.")

    amount = float(data.amount or 0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Le montant payé doit être positif.")
    paid_amount = sum(float(payment.amount or 0) for payment in invoice.payments)
    remaining_amount = max(float(invoice.total_amount or 0) - paid_amount, 0.0)
    if remaining_amount <= 0:
        raise HTTPException(status_code=400, detail="Cette facture fournisseur est déjà payée.")
    if amount > remaining_amount:
        raise HTTPException(status_code=400, detail=f"Paiement supérieur au reste à payer ({remaining_amount:.2f}).")

    payment = models.SupplierPayment(
        supplier_invoice_id=invoice.id,
        supplier=invoice.supplier,
        amount=amount,
        method=(data.method or "TRANSFER").upper(),
        reference=(data.reference or "").strip() or None,
        notes=data.notes,
        payment_date=data.payment_date or utcnow(),
        created_by=current_user.get("sub", "unknown"),
    )
    db.add(payment)
    new_paid_amount = paid_amount + amount
    invoice.status = "PAID" if new_paid_amount >= float(invoice.total_amount or 0) else "PARTIAL"
    db.commit()
    db.refresh(invoice)
    return _serialize_supplier_invoice(invoice)

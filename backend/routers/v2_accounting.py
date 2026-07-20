from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import datetime, timedelta
import csv
import io

from ..database import get_db
from .. import models, schemas
from ..core import security
from ..services.document_sequences import next_number
from ..services import nf525_seal
from ..core.time import utcnow

router = APIRouter(
    prefix="/v2/accounting",
    tags=["accounting"],
    dependencies=[Depends(security.get_current_user)],
)

# --- FACTURATION ---

def generate_invoice_reference(db: Session):
    # Format: F-YYYY-XXXX — séquence transactionnelle inaltérable (NF525)
    return next_number(db, "invoice")

def generate_avoir_reference(db: Session):
    # Format: AV-YYYY-XXXX — séquence transactionnelle inaltérable (NF525)
    return next_number(db, "credit_note")

def compute_qr_seal(db: Session, invoice: models.Invoice):
    # Sceau NF525 : HMAC-SHA256 à clé secrète, chaîné à la pièce précédente,
    # calculé sur les seules données immuables (pas de status).
    return nf525_seal.seal_invoice(db, invoice)

def _find_returned_delivery_note(db: Session, invoice: models.Invoice) -> Optional[models.DeliveryNote]:
    if not invoice.sale_order_id:
        return None
    return (
        db.query(models.DeliveryNote)
        .filter(
            models.DeliveryNote.sale_order_id == invoice.sale_order_id,
            models.DeliveryNote.status == "RETURNED",
        )
        .order_by(models.DeliveryNote.id.desc())
        .first()
    )

def _resolve_credit_note_delivery_note(
    db: Session,
    invoice: models.Invoice,
    delivery_note_id: Optional[int],
) -> Optional[models.DeliveryNote]:
    if delivery_note_id is None:
        return _find_returned_delivery_note(db, invoice)

    delivery_note = db.query(models.DeliveryNote).filter(models.DeliveryNote.id == delivery_note_id).first()
    if not delivery_note:
        raise HTTPException(404, "Bon de livraison introuvable")
    if delivery_note.status != "RETURNED":
        raise HTTPException(400, "L'avoir de retour client doit être lié à un bon de livraison retourné.")
    if invoice.sale_order_id and delivery_note.sale_order_id != invoice.sale_order_id:
        raise HTTPException(400, "Le bon de livraison retourné n'est pas lié au devis de la facture.")
    return delivery_note

def _find_return_move(db: Session, invoice: models.Invoice) -> Optional[models.StockMove]:
    if not invoice.sale_order_id:
        return None
    reservation = (
        db.query(models.StockReservation)
        .filter(
            models.StockReservation.sale_order_id == invoice.sale_order_id,
            models.StockReservation.source_label.in_(["devis libre", "devis_libre"]),
            models.StockReservation.status == "returned",
        )
        .order_by(models.StockReservation.id.desc())
        .first()
    )
    if not reservation:
        return None
    return (
        db.query(models.StockMove)
        .filter(
            models.StockMove.reference.like("RETOUR-CLIENT%"),
            models.StockMove.notes.contains(reservation.reference),
        )
        .order_by(models.StockMove.id.desc())
        .first()
    )

def _returned_sale_order_lines(db: Session, sale_order_id: int) -> list[tuple[models.SaleOrderLine, float]]:
    reservation = (
        db.query(models.StockReservation)
        .options(joinedload(models.StockReservation.lines))
        .filter(
            models.StockReservation.sale_order_id == sale_order_id,
            models.StockReservation.source_label.in_(["devis libre", "devis_libre"]),
            models.StockReservation.status == "returned",
        )
        .order_by(models.StockReservation.id.desc())
        .first()
    )
    if not reservation:
        return []

    returned_lines = []
    for line in reservation.lines:
        if line.status != "returned" or not line.source or not line.source.startswith("sale_order_line:"):
            continue
        try:
            sale_line_id = int(line.source.split(":", 1)[1])
        except ValueError:
            continue
        sale_line = db.query(models.SaleOrderLine).filter(models.SaleOrderLine.id == sale_line_id).first()
        returned_quantity = float(line.consumed_quantity or line.reserved_quantity or 0)
        if sale_line and returned_quantity > 0:
            returned_lines.append((sale_line, returned_quantity))
    return returned_lines

@router.get("/invoices", response_model=List[schemas.InvoiceResponse])
def get_invoices(db: Session = Depends(get_db)):
    return db.query(models.Invoice).order_by(models.Invoice.issue_date.desc()).all()

@router.post("/invoices", response_model=schemas.InvoiceResponse)
def create_invoice(invoice: schemas.InvoiceCreate, db: Session = Depends(get_db), role: str = Depends(security.get_current_user_role)):
    if role not in ["ADMIN", "MANAGER"]:
        raise HTTPException(status_code=403, detail="Seul un manager ou un administrateur peut créer une facture.")

    # Calculate Totals
    subtotal = sum(l.unit_price * l.quantity for l in invoice.lines)
    tax_amount = sum(l.unit_price * l.quantity * (l.tax_rate / 100.0) for l in invoice.lines)
    total = subtotal + tax_amount

    new_invoice = models.Invoice(
        reference=generate_invoice_reference(db),
        sale_order_id=invoice.sale_order_id,
        client_name=invoice.client_name,
        client_address=invoice.client_address,
        client_siret=invoice.client_siret,
        due_date=invoice.due_date,
        status="UNPAID",
        invoice_type=invoice.invoice_type or "FINAL",
        subtotal=subtotal,
        tax_rate=invoice.lines[0].tax_rate if invoice.lines else 20.0,
        tax_amount=tax_amount,
        total=total
    )
    db.add(new_invoice)
    db.flush()

    for line in invoice.lines:
        db_line = models.InvoiceLine(
            invoice_id=new_invoice.id,
            description=line.description,
            quantity=line.quantity,
            unit_price=line.unit_price,
            tax_rate=line.tax_rate
        )
        db.add(db_line)
        
    # Generate Seal
    new_invoice.qr_code_hash = compute_qr_seal(db, new_invoice)
    
    db.commit()
    db.refresh(new_invoice)
    return new_invoice

@router.post("/invoices/{invoice_id}/pay", response_model=schemas.InvoiceResponse)
def add_payment(invoice_id: int, payment: schemas.PaymentCreate, db: Session = Depends(get_db), role: str = Depends(security.get_current_user_role)):
    if role not in ["ADMIN", "MANAGER"]:
        raise HTTPException(status_code=403, detail="Seul un manager peut encaisser un paiement.")

    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(404, "Facture introuvable")
        
    if invoice.status == "PAID":
        raise HTTPException(400, "Cette facture est déjà intégralement payée.")

    new_payment = models.Payment(
        invoice_id=invoice.id,
        amount=payment.amount,
        method=payment.method,
        reference=payment.reference
    )
    db.add(new_payment)
    db.flush()

    # Calculate new status
    total_paid = sum(float(p.amount or 0) for p in invoice.payments) + payment.amount
    if total_paid >= float(invoice.total or 0):
        invoice.status = "PAID"
    else:
        invoice.status = "PARTIAL"

    # NF525 : le sceau est immuable — il porte sur les données inaltérables
    # (référence, client, date, montants), pas sur le status. Un encaissement
    # ne doit JAMAIS déclencher de re-scellage.

    db.commit()
    db.refresh(invoice)
    return invoice

@router.post("/invoices/{invoice_id}/remind")
def send_reminder(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(404, "Facture introuvable")
    
    # In a real app, this sends an email via an EmailService.
    # Here we simulate the reminder.
    log = models.ChatterMessage(
        model_name="invoice",
        record_id=invoice.id,
        body=f"Relance de paiement envoyée au client pour la facture {invoice.reference}.",
        author="System"
    )
    db.add(log)
    db.commit()
    return {"message": "Relance envoyée avec succès"}

@router.post("/invoices/{invoice_id}/credit_note", response_model=schemas.InvoiceResponse)
def create_credit_note(
    invoice_id: int,
    credit_note: Optional[schemas.CreditNoteCreate] = None,
    db: Session = Depends(get_db),
    role: str = Depends(security.get_current_user_role),
):
    if role not in ["ADMIN", "MANAGER"]:
        raise HTTPException(status_code=403, detail="Seul un manager peut émettre un avoir.")

    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(404, "Facture introuvable")

    if invoice.status == "AVOIR":
        raise HTTPException(400, "Cette pièce est déjà un avoir.")

    delivery_note = _resolve_credit_note_delivery_note(
        db,
        invoice,
        credit_note.delivery_note_id if credit_note else None,
    )
    existing_credit_note = (
        db.query(models.Invoice)
        .filter(
            models.Invoice.status == "AVOIR",
            models.Invoice.source_invoice_id == invoice.id,
            models.Invoice.delivery_note_id == (delivery_note.id if delivery_note else None),
        )
        .first()
    )
    if existing_credit_note:
        raise HTTPException(400, f"Un avoir existe déjà pour cette facture: {existing_credit_note.reference}.")

    returned_sale_lines = _returned_sale_order_lines(db, invoice.sale_order_id) if delivery_note and invoice.sale_order_id else []
    if returned_sale_lines:
        credit_lines = [
            {
                "description": f"Avoir sur: {sale_line.description}",
                "quantity": quantity,
                "unit_price": -float(sale_line.unit_price or 0) * (1 - float(sale_line.discount_pct or 0) / 100),
                "tax_rate": invoice.tax_rate,
            }
            for sale_line, quantity in returned_sale_lines
        ]
    else:
        credit_lines = [
            {
                "description": f"Avoir sur: {line.description}",
                "quantity": line.quantity,
                "unit_price": -float(line.unit_price or 0),
                "tax_rate": line.tax_rate,
            }
            for line in invoice.lines
        ]

    subtotal = sum(line["unit_price"] * line["quantity"] for line in credit_lines)
    tax_amount = sum(line["unit_price"] * line["quantity"] * (line["tax_rate"] / 100.0) for line in credit_lines)
    total = subtotal + tax_amount

    # Create AVOIR
    return_move = _find_return_move(db, invoice) if delivery_note else None
    avoir = models.Invoice(
        reference=generate_avoir_reference(db),
        sale_order_id=invoice.sale_order_id,
        source_invoice_id=invoice.id,
        delivery_note_id=delivery_note.id if delivery_note else None,
        return_move_id=return_move.id if return_move else None,
        client_name=invoice.client_name,
        client_address=invoice.client_address,
        client_siret=invoice.client_siret,
        issue_date=utcnow(),
        due_date=utcnow(),
        status="AVOIR",
        invoice_type="CREDIT_NOTE",
        subtotal=subtotal,
        tax_rate=invoice.tax_rate,
        tax_amount=tax_amount,
        total=total
    )
    db.add(avoir)
    db.flush()

    for line in credit_lines:
        db_line = models.InvoiceLine(
            invoice_id=avoir.id,
            description=line["description"],
            quantity=line["quantity"],
            unit_price=line["unit_price"],
            tax_rate=line["tax_rate"]
        )
        db.add(db_line)
        
    avoir.qr_code_hash = compute_qr_seal(db, avoir)
    
    db.commit()
    db.refresh(avoir)
    return avoir

@router.post("/invoices/{invoice_id}/credit-note-from-return", response_model=schemas.InvoiceResponse)
def create_credit_note_from_return(
    invoice_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(security.get_current_user_role),
):
    if role not in ["ADMIN", "MANAGER"]:
        raise HTTPException(status_code=403, detail="Seul un manager peut émettre un avoir.")

    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(404, "Facture introuvable")
    if invoice.status == "AVOIR":
        raise HTTPException(400, "Cette pièce est déjà un avoir.")

    delivery_note = _find_returned_delivery_note(db, invoice)
    if not delivery_note:
        raise HTTPException(400, "Aucun bon de livraison retourné lié à cette facture.")

    return_move = _find_return_move(db, invoice)
    if not return_move:
        raise HTTPException(400, "Aucun mouvement RETOUR-CLIENT lié à cette facture.")

    avoir = create_credit_note(
        invoice_id=invoice_id,
        credit_note=schemas.CreditNoteCreate(delivery_note_id=delivery_note.id),
        db=db,
        role=role,
    )
    return avoir

@router.get("/export/fec")
def export_fec(db: Session = Depends(get_db), role: str = Depends(security.get_current_user_role)):
    if role != "ADMIN":
        raise HTTPException(status_code=403, detail="Réservé à l'administrateur système.")
        
    # Fichier des Écritures Comptables (Simplified)
    # JournalCode|JournalLib|EcritureNum|EcritureDate|CompteNum|CompteLib|CompAuxNum|CompAuxLib|PieceRef|PieceDate|EcritureLib|Debit|Credit|EcritureLet|DateLet|ValidDate|Montantdevise|Idevise
    
    invoices = db.query(models.Invoice).filter(models.Invoice.status != "DRAFT").all()
    
    output = io.StringIO()
    writer = csv.writer(output, delimiter='|')
    
    writer.writerow([
        "JournalCode", "JournalLib", "EcritureNum", "EcritureDate", 
        "CompteNum", "CompteLib", "CompAuxNum", "CompAuxLib", 
        "PieceRef", "PieceDate", "EcritureLib", 
        "Debit", "Credit", "EcritureLet", "DateLet", "ValidDate", "Montantdevise", "Idevise"
    ])
    
    for inv in invoices:
        date_str = inv.issue_date.strftime("%Y%m%d")
        
        # Ligne Client (Débit)
        writer.writerow([
            "VT", "Ventes", f"ECR-{inv.id}", date_str,
            "411000", "Clients", "", "",
            inv.reference, date_str, f"Facture {inv.reference} - {inv.client_name}",
            f"{inv.total:.2f}", "0.00", "", "", date_str, "", ""
        ])
        
        # Ligne Vente HT (Crédit)
        writer.writerow([
            "VT", "Ventes", f"ECR-{inv.id}", date_str,
            "701000", "Ventes de produits finis", "", "",
            inv.reference, date_str, f"Facture {inv.reference} - {inv.client_name}",
            "0.00", f"{inv.subtotal:.2f}", "", "", date_str, "", ""
        ])
        
        # Ligne TVA (Crédit)
        if inv.tax_amount > 0:
            writer.writerow([
                "VT", "Ventes", f"ECR-{inv.id}", date_str,
                "445710", "TVA collectée", "", "",
                inv.reference, date_str, f"Facture {inv.reference} - {inv.client_name}",
                "0.00", f"{inv.tax_amount:.2f}", "", "", date_str, "", ""
            ])
            
    # Include Payments in Treasury Journal
    payments = db.query(models.Payment).all()
    for pay in payments:
        inv = pay.invoice
        date_str = pay.payment_date.strftime("%Y%m%d")
        
        # Banque (Débit)
        writer.writerow([
            "BQ", "Banque", f"PAY-{pay.id}", date_str,
            "512000", "Banque", "", "",
            pay.reference or f"PAY-{pay.id}", date_str, f"Paiement {pay.method} Facture {inv.reference}",
            f"{pay.amount:.2f}", "0.00", "", "", date_str, "", ""
        ])
        
        # Client (Crédit)
        writer.writerow([
            "BQ", "Banque", f"PAY-{pay.id}", date_str,
            "411000", "Clients", "", "",
            pay.reference or f"PAY-{pay.id}", date_str, f"Paiement {pay.method} Facture {inv.reference}",
            "0.00", f"{pay.amount:.2f}", "", "", date_str, "", ""
        ])

    response = Response(content=output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename=FEC_MMG_{utcnow().strftime('%Y%m')}.txt"
    response.headers["Content-Type"] = "text/csv"
    return response

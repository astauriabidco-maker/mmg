from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta
import hashlib
import json
import csv
import io

from ..database import get_db
from .. import models, schemas
from ..core import security

router = APIRouter(prefix="/v2/accounting", tags=["accounting"])

# --- FACTURATION ---

def generate_invoice_reference(db: Session):
    # Format: F-YYYY-XXXX (Chrono continuous per year)
    year = datetime.utcnow().year
    count = db.query(models.Invoice).filter(models.Invoice.reference.like(f"F-{year}-%")).count()
    return f"F-{year}-{count + 1:04d}"

def compute_qr_seal(invoice: models.Invoice):
    # NF525 Anti-fraud signature
    data = f"{invoice.reference}|{invoice.client_name}|{invoice.issue_date.isoformat()}|{invoice.total}|{invoice.status}"
    return hashlib.sha256(data.encode()).hexdigest()

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
    new_invoice.qr_code_hash = compute_qr_seal(new_invoice)
    
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
    total_paid = sum(p.amount for p in invoice.payments) + payment.amount
    if total_paid >= invoice.total:
        invoice.status = "PAID"
    else:
        invoice.status = "PARTIAL"
        
    # Re-seal
    invoice.qr_code_hash = compute_qr_seal(invoice)

    db.commit()
    db.refresh(invoice)
    return invoice

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
    response.headers["Content-Disposition"] = f"attachment; filename=FEC_MMG_{datetime.utcnow().strftime('%Y%m')}.txt"
    response.headers["Content-Type"] = "text/csv"
    return response

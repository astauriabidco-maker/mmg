from io import BytesIO
from datetime import timedelta
from typing import Optional
from xml.sax.saxutils import escape
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from ..database import get_db
from .. import models

router = APIRouter(prefix="/v2/pdf", tags=["PDF"])

QUOTE_STATUS_LABELS = {
    "DRAFT": "Brouillon",
    "SENT": "Envoyé au client",
    "VALIDATED": "Signé / validé",
    "ACCEPTED": "Accepté",
    "CANCELLED": "Annulé",
    "IN_DESIGN": "Bureau d'études",
    "READY_FOR_PROD": "Prêt pour production",
    "IN_PRODUCTION": "En production",
}


def _money(value: float, currency: str = "EUR") -> str:
    return f"{float(value or 0):,.2f} {currency}".replace(",", " ").replace(".", ",")


def _percent(value: float) -> str:
    return f"{float(value or 0):g}".replace(".", ",")


def _line_type_label(line_type: Optional[str]) -> str:
    return "Article stock" if (line_type or "").upper() == "STOCK_ITEM" else "Prestation"


def _line_net_total(line: models.SaleOrderLine) -> float:
    gross = float(line.quantity or 0) * float(line.unit_price or 0)
    discount = max(min(float(line.discount_pct or 0), 100), 0)
    return gross * (1 - discount / 100)


def _variant_reference(line: models.SaleOrderLine) -> str:
    if not line.variant:
        return ""
    if line.variant.reference:
        return line.variant.reference
    product = line.variant.product
    return product.reference_base if product else ""


@router.get("/quote/{sale_id}")
def generate_quote_pdf(sale_id: int, db: Session = Depends(get_db)):
    sale = db.query(models.SaleOrder).filter(models.SaleOrder.id == sale_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="SaleOrder not found")

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        name='TitleStyle',
        parent=styles['Heading1'],
        fontSize=22,
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=12,
    )
    normal_style = styles["Normal"]
    small_style = ParagraphStyle(name="SmallStyle", parent=styles["Normal"], fontSize=8, leading=10)
    muted_style = ParagraphStyle(name="MutedStyle", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#64748b"))

    status_label = QUOTE_STATUS_LABELS.get(sale.status, sale.status)
    valid_until = sale.created_at + timedelta(days=sale.validity_days or 30)
    currency = sale.currency or "EUR"
    tax_rate = float(sale.tax_rate if sale.tax_rate is not None else 20.0)

    # --- HEADER ---
    header_data = [
        [
            Paragraph("<b>MMG MENUISERIES</b><br/>123 Zone Industrielle<br/>75000 PARIS<br/>Tél: 01 23 45 67 89", normal_style),
            Paragraph(
                f"<b>DEVIS CLIENT</b><br/>"
                f"Réf: {escape(sale.reference)}<br/>"
                f"Statut: {escape(status_label)}<br/>"
                f"Date: {sale.created_at.strftime('%d/%m/%Y')}<br/>"
                f"Valable jusqu'au: {valid_until.strftime('%d/%m/%Y')}",
                normal_style,
            )
        ]
    ]
    header_table = Table(header_data, colWidths=[300, 200])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 30))
    
    # --- CLIENT INFO ---
    client_info = (
        "<b>À l'attention de :</b><br/>"
        f"{escape(sale.client_name or 'Client non renseigné')}<br/>"
        f"{escape(sale.client_address or 'Adresse non renseignée')}<br/>"
        f"{escape(sale.client_contact or '')}"
        f"{' - ' if sale.client_contact and sale.client_email else ''}"
        f"{escape(sale.client_email or '')}"
    )
    elements.append(Paragraph(client_info, normal_style))
    elements.append(Spacer(1, 22))
    
    # --- TITLE ---
    elements.append(Paragraph(f"DEVIS N° {sale.reference}", title_style))
    elements.append(Paragraph("Pièces, accessoires, prestations et conditions commerciales", muted_style))
    elements.append(Spacer(1, 18))
    
    # --- ITEMS TABLE ---
    table_data = [["Type", "Réf.", "Description", "Qté", "PU HT", "Remise", "Total HT"]]
    
    total_ht = 0
    for line in sale.lines:
        line_total = _line_net_total(line)
        total_ht += line_total
        reference = _variant_reference(line)
        table_data.append([
            Paragraph(escape(_line_type_label(line.line_type)), small_style),
            Paragraph(escape(reference or "-"), small_style),
            Paragraph(escape(line.description or ""), normal_style),
            f"{float(line.quantity or 0):g}",
            _money(line.unit_price, currency),
            f"{float(line.discount_pct or 0):g} %",
            _money(line_total, currency),
        ])
        
    t = Table(table_data, colWidths=[68, 70, 186, 42, 64, 52, 72], repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor("#334155")),
        ('ALIGN', (3, 1), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1"))
    ]))
    elements.append(t)
    elements.append(Spacer(1, 20))
    
    # --- TOTALS ---
    tva = total_ht * (tax_rate / 100)
    total_ttc = total_ht + tva
    
    totals_data = [
        ["Total HT:", _money(total_ht, currency)],
        [f"TVA ({_percent(tax_rate)}%):", _money(tva, currency)],
        ["Total TTC:", _money(total_ttc, currency)]
    ]
    totals_table = Table(totals_data, colWidths=[100, 100])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 2), (-1, 2), 12),
        ('TEXTCOLOR', (0, 2), (-1, 2), colors.HexColor("#1e293b")),
        ('TOPPADDING', (0, 2), (-1, 2), 10),
        ('LINEABOVE', (0, 2), (-1, 2), 1, colors.HexColor("#1e293b")),
    ]))
    
    # Push totals to the right
    wrapper_table = Table([["", totals_table]], colWidths=[310, 200])
    elements.append(wrapper_table)
    
    if sale.notes:
        elements.append(Spacer(1, 22))
        elements.append(Paragraph("<b>Notes commerciales</b>", normal_style))
        elements.append(Paragraph(escape(sale.notes).replace("\n", "<br/>"), normal_style))

    # --- FOOTER ---
    elements.append(Spacer(1, 28))
    footer_text = (
        "<b>Conditions de vente</b><br/>"
        "Acompte selon accord commercial, solde à la livraison, pose ou fin d'intervention.<br/>"
        f"Validité du devis: {sale.validity_days or 30} jours. "
        "Les articles stock sont réservés uniquement après validation/signature du devis, "
        "dans la limite des disponibilités constatées.<br/><br/>"
        "Signature précédée de la mention \"Bon pour accord\" :"
    )
    elements.append(Paragraph(footer_text, normal_style))
    
    # Build PDF
    doc.build(elements)
    
    pdf_value = buffer.getvalue()
    buffer.close()
    
    return Response(
        content=pdf_value,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=Devis_{sale.reference}.pdf"
        }
    )

@router.get("/invoice/{invoice_id}")
def generate_invoice_pdf(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        name='TitleStyle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=20,
    )
    
    normal_style = styles["Normal"]
    
    # --- HEADER ---
    header_data = [
        [
            Paragraph("<b>MMG MENUISERIES</b><br/>123 Zone Industrielle<br/>75000 PARIS<br/>Tél: 01 23 45 67 89", normal_style),
            Paragraph(f"<b>FACTURE CLIENT</b><br/>Réf: {invoice.reference}<br/>Date: {invoice.issue_date.strftime('%d/%m/%Y')}", normal_style)
        ]
    ]
    header_table = Table(header_data, colWidths=[300, 200])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 30))
    
    # --- CLIENT INFO ---
    client_info = f"""
    <b>Facturé à :</b><br/>
    {invoice.client_name}<br/>
    {invoice.client_address or 'Adresse non renseignée'}<br/>
    {('SIRET: ' + invoice.client_siret) if invoice.client_siret else ''}
    """
    elements.append(Paragraph(client_info, normal_style))
    elements.append(Spacer(1, 30))
    
    # --- TITLE ---
    elements.append(Paragraph(f"FACTURE N° {invoice.reference}", title_style))
    elements.append(Spacer(1, 20))
    
    # --- ITEMS TABLE ---
    table_data = [["Description", "Quantité", "Prix Unitaire (HT)", "Total (HT)"]]
    
    for line in invoice.lines:
        line_total = line.quantity * line.unit_price
        table_data.append([
            Paragraph(line.description, normal_style),
            str(line.quantity),
            f"{line.unit_price:.2f} €",
            f"{line_total:.2f} €"
        ])
        
    t = Table(table_data, colWidths=[280, 70, 80, 80])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor("#334155")),
        ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('TOPPADDING', (0, 1), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1"))
    ]))
    elements.append(t)
    elements.append(Spacer(1, 20))
    
    # --- TOTALS ---
    totals_data = [
        ["Total HT:", f"{invoice.subtotal:.2f} €"],
        [f"TVA ({invoice.tax_rate}%):", f"{invoice.tax_amount:.2f} €"],
        ["Total TTC:", f"{invoice.total:.2f} €"]
    ]
    
    total_paid = sum(p.amount for p in invoice.payments)
    remainder = invoice.total - total_paid
    
    totals_data.append(["Déjà Payé:", f"- {total_paid:.2f} €"])
    totals_data.append(["Reste à payer:", f"{remainder:.2f} €"])
    
    totals_table = Table(totals_data, colWidths=[100, 100])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 2), (-1, 2), 12),
        ('TEXTCOLOR', (0, 2), (-1, 2), colors.HexColor("#1e293b")),
        ('TOPPADDING', (0, 2), (-1, 2), 10),
        ('LINEABOVE', (0, 2), (-1, 2), 1, colors.HexColor("#1e293b")),
        ('FONTNAME', (0, 4), (-1, 4), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 4), (-1, 4), colors.HexColor("#dc2626")), # Red for remainder
    ]))
    
    wrapper_table = Table([["", totals_table]], colWidths=[310, 200])
    elements.append(wrapper_table)
    
    # --- FOOTER ---
    elements.append(Spacer(1, 40))
    footer_text = f"""
    <b>Mentions Légales:</b><br/>
    En cas de retard de paiement, indemnité forfaitaire pour frais de recouvrement: 40 euros.<br/>
    <br/>
    """
    if invoice.qr_code_hash:
        footer_text += f"<font size='7' color='gray'>Signature NF525: {invoice.qr_code_hash}</font>"
        
    elements.append(Paragraph(footer_text, normal_style))
    
    doc.build(elements)
    
    pdf_value = buffer.getvalue()
    buffer.close()
    
    return Response(
        content=pdf_value,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=Facture_{invoice.reference}.pdf"
        }
    )

import os
from io import BytesIO
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

from ..database import get_db
from .. import models

router = APIRouter(prefix="/v2/pdf", tags=["PDF"])

@router.get("/quote/{sale_id}")
def generate_quote_pdf(sale_id: int, db: Session = Depends(get_db)):
    sale = db.query(models.SaleOrder).filter(models.SaleOrder.id == sale_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="SaleOrder not found")

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom Styles
    title_style = ParagraphStyle(
        name='TitleStyle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=20,
    )
    
    normal_style = styles["Normal"]
    bold_style = ParagraphStyle(name='BoldStyle', parent=styles['Normal'], fontName='Helvetica-Bold')
    
    # --- HEADER ---
    header_data = [
        [
            Paragraph("<b>MMG MENUISERIES</b><br/>123 Zone Industrielle<br/>75000 PARIS<br/>Tél: 01 23 45 67 89", normal_style),
            Paragraph(f"<b>DEVIS CLIENT</b><br/>Réf: {sale.reference}<br/>Date: {sale.created_at.strftime('%d/%m/%Y')}", normal_style)
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
    <b>À l'attention de :</b><br/>
    {sale.client_name}<br/>
    {sale.client_address or 'Adresse non renseignée'}<br/>
    {sale.client_contact or ''} - {sale.client_email or ''}
    """
    elements.append(Paragraph(client_info, normal_style))
    elements.append(Spacer(1, 30))
    
    # --- TITLE ---
    elements.append(Paragraph(f"DEVIS N° {sale.reference}", title_style))
    elements.append(Spacer(1, 20))
    
    # --- ITEMS TABLE ---
    table_data = [["Description", "Quantité", "Prix Unitaire (HT)", "Total (HT)"]]
    
    total_ht = 0
    for line in sale.lines:
        line_total = line.quantity * line.unit_price
        total_ht += line_total
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
    tva = total_ht * 0.20
    total_ttc = total_ht + tva
    
    totals_data = [
        ["Total HT:", f"{total_ht:.2f} €"],
        ["TVA (20%):", f"{tva:.2f} €"],
        ["Total TTC:", f"{total_ttc:.2f} €"]
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
    
    # --- FOOTER ---
    elements.append(Spacer(1, 40))
    footer_text = """
    <b>Conditions de Vente:</b><br/>
    Acompte de 40% à la commande, solde à la livraison/pose.<br/>
    Validité du devis: 30 jours.<br/>
    <br/>
    Signature précédée de la mention "Bon pour accord" :
    """
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

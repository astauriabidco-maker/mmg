from io import BytesIO
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from backend.services.commercial_quote_analysis import (
    compare_commercial_quote_versions,
)
from backend.services.technical_document_analysis import analyze_technical_document


def _pdf(lines: list[str]) -> bytes:
    buffer = BytesIO()
    document = canvas.Canvas(buffer)
    y = 800
    for line in lines:
        document.drawString(36, y, line)
        y -= 22
        if y < 50:
            document.showPage()
            y = 800
    document.save()
    return buffer.getvalue()


def _write_pdf(tmp_path: Path, name: str, lines: list[str]) -> Path:
    path = tmp_path / name
    path.write_bytes(_pdf(lines))
    return path


def test_anonymized_proges_pdf_is_detected_and_normalized(tmp_path):
    path = _write_pdf(
        tmp_path,
        "proges-pvc-anonymise.pdf",
        [
            "Devis N° PVC-ANON-001",
            "CLIENT ANONYMISE",
            "Qté Désignation L H P.U. HT P.T. HT",
            "F01",
            "2 KOMMERLING 76 ADVANCED 1200 1400 650,00 1 300,00",
            "Fenêtre OB 2 vantaux",
            "PF01",
            "1 Porte fenêtre PVC 1800 2150 900,00 900,00",
            "MONTANT TOTAL H.T. 2 200,00 €",
            "REMISE : 200,00 €",
            "MONTANT TOTAL H.T. 2 000,00 €",
            "T.V.A. à 20,00 % 400,00 €",
            "MONTANT TOTAL T.T.C. 2 400,00 €",
        ],
    )

    analysis = analyze_technical_document(path, "QUOTING", "")

    assert analysis.status == "PARSED"
    assert analysis.detected_source_system == "PROGES"
    assert analysis.detected_project_reference == "PVC-ANON-001"
    assert analysis.summary["line_count"] == 2
    assert analysis.summary["total_quantity"] == 3
    assert analysis.summary["subtotal_before_discount"] == pytest.approx(2200)
    assert analysis.summary["subtotal_after_discount"] == pytest.approx(2000)
    assert analysis.summary["grand_total"] == pytest.approx(2400)
    assert analysis.records[0]["position"] == "F01"
    assert analysis.records[0]["width_mm"] == 1200
    assert analysis.records[0]["unit_price"] == pytest.approx(650)
    assert analysis.issues == []


def test_anonymized_orgadata_pdf_is_detected_and_normalized(tmp_path):
    path = _write_pdf(
        tmp_path,
        "orgadata-alu-anonymise.pdf",
        [
            "DEVIS N°ALU-ANON-002 - CLIENT ANONYMISE",
            "Position Quantité Description Prix Total",
            "[EUR] [EUR]",
            "CH1 / CH2 2 Pce 1 250,00 2 500,00",
            "Vue intérieure",
            "châssis 900 mm x 2100 mm, comprenant une fenêtre OF.",
            "Système: Cortizo COR 70 INDUSTRIAL",
            "RAL 7016",
            "PF1 1 Pce 2 500,00 2 500,00",
            "Vue intérieure",
            "porte-fenêtre 1200 mm x 2380 mm.",
            "Système: Cortizo COR 70 INDUSTRIAL",
            "Total HT 5 000,00 EUR",
            "Remise Excep.: - 20,00 % -1 000,00 EUR",
            "Total HT net 4 000,00 EUR",
            "T.V.A. 20,00 % 800,00 EUR",
            "Prix total 4 800,00 EUR",
        ],
    )

    analysis = analyze_technical_document(path, "QUOTING", "")

    assert analysis.status == "PARSED"
    assert analysis.detected_source_system == "ORGADATA"
    assert analysis.detected_project_reference == "ALU-ANON-002"
    assert analysis.summary["line_count"] == 2
    assert analysis.summary["total_quantity"] == 3
    assert analysis.summary["effective_discount_pct"] == pytest.approx(20)
    assert analysis.summary["subtotal_after_discount"] == pytest.approx(4000)
    assert analysis.records[0]["position"] == "CH1 / CH2"
    assert analysis.records[0]["height_mm"] == 2100
    assert analysis.records[1]["total_price"] == pytest.approx(2500)
    assert analysis.issues == []


def test_commercial_quote_comparison_reports_price_changes():
    previous = [
        {"position": "F01", "quantity": 1, "unit_price": 650, "total_price": 650},
        {"position": "PF01", "quantity": 1, "unit_price": 900, "total_price": 900},
    ]
    current = [
        {"position": "F01", "quantity": 1, "unit_price": 650, "total_price": 650},
        {"position": "PF01", "quantity": 1, "unit_price": 950, "total_price": 950},
    ]

    comparison = compare_commercial_quote_versions(previous, current)

    assert comparison["has_changes"] is True
    assert comparison["changed_count"] == 1
    assert comparison["total_delta"] == pytest.approx(50)

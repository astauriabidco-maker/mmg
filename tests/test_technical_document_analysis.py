from backend.services.technical_document_analysis import analyze_technical_document


def test_analyze_sepver_extracts_controlled_material_data(tmp_path):
    path = tmp_path / "SEPVER.TXT"
    path.write_text(
        """MMG
SEPALUMIC GAMME BASE
VER DIMASCIO
22-04-2026

RAL 8017S Satiné (+25%);7007;BAVETTE DE FAITAGE;3;barre  6,50
Brut ( Q-U );70501;JOINT DE BAVETTE;50;ml
""",
        encoding="latin-1",
    )

    analysis = analyze_technical_document(path, "CUTTING", "OTHER")

    assert analysis.status == "PARSED"
    assert analysis.detected_document_type == "CUTTING"
    assert analysis.detected_source_system == "PROGES"
    assert analysis.detected_project_reference == "VER DIMASCIO"
    assert analysis.summary["debit_lines"] == 2
    assert analysis.summary["total_quantity"] == 53
    assert [record["reference"] for record in analysis.records] == ["7007", "70501"]


def test_fabrication_pdf_remains_consultable_without_stock_records(tmp_path, monkeypatch):
    path = tmp_path / "Bon d'atelier.pdf"
    path.write_bytes(b"%PDF-test")
    monkeypatch.setattr(
        "backend.services.technical_document_analysis._document_text",
        lambda _path: "ORGADATA LogiKal\nBon d'atelier\nAffaire: MMG26020068NC",
    )

    analysis = analyze_technical_document(path, "FABRICATION", "ORGADATA")

    assert analysis.status == "DOCUMENT_ONLY"
    assert analysis.detected_document_type == "FABRICATION"
    assert analysis.detected_source_system == "ORGADATA"
    assert analysis.detected_project_reference == "MMG26020068NC"
    assert analysis.records == []


def test_unrecognized_cutting_document_is_not_approvable(tmp_path):
    path = tmp_path / "debit-inconnu.txt"
    path.write_text("document libre sans lignes matière", encoding="utf-8")

    analysis = analyze_technical_document(path, "CUTTING", "OTHER")

    assert analysis.status == "FAILED"
    assert analysis.records == []
    assert analysis.issues


def test_valuation_pdf_detects_reference_despite_pdf_encoding(tmp_path, monkeypatch):
    path = tmp_path / "VALO_VER.pdf"
    path.write_bytes(b"%PDF-test")
    monkeypatch.setattr(
        "backend.services.technical_document_analysis._document_text",
        lambda _path: (
            "VALORISATION DE COMMANDE\n"
            "Fournisseur : SEPALUMIC GAMME BASE\n"
            "RØfØrence Commande : VER DIMASCIO"
        ),
    )

    analysis = analyze_technical_document(path, "VALUATION", "PROGES")

    assert analysis.status == "DOCUMENT_ONLY"
    assert analysis.detected_document_type == "VALUATION"
    assert analysis.detected_project_reference == "VER DIMASCIO"


def test_cortizo_purchase_bom_is_internal_cutting_requirement(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "commande-cortizo-anonymisee.pdf"
    path.write_bytes(b"%PDF-test")
    text = """AFFAIRE N°MMG26070003V1 - CLIENT TEST
Commande
Nom affaire: ALIAS TEST
Ferrure
Croquis Quantité / Numéro Description Teinte Prix Total
Unité [EUR] [EUR]
2 pce (2) 123456 Article direct 1,00 2,00
Accessoires
Croquis Quantité / Numéro Description Teinte Prix Total
Unité [EUR] [EUR]
(Nécessaire)
1 UV á 25 pce 654321 Article conditionné 0,50 12,50
(8)
"""
    monkeypatch.setattr(
        "backend.services.technical_document_analysis._document_text",
        lambda _path: text,
    )
    monkeypatch.setattr(
        "scripts.import_workshop_debits.extract_pdf_text",
        lambda _path: text,
    )

    # A manual ORGADATA selection must not turn this derived Word document
    # into proof that ORGADATA generated it.
    analysis = analyze_technical_document(path, "CUTTING", "ORGADATA")

    assert analysis.status == "PARSED"
    assert analysis.detected_document_type == "CUTTING"
    assert analysis.detected_source_system == "INTERNAL"
    assert analysis.detected_project_reference == "MMG26070003V1"
    assert analysis.summary["debit_lines"] == 2
    assert analysis.summary["total_quantity"] == 10
    assert [record["quantity"] for record in analysis.records] == [2, 8]

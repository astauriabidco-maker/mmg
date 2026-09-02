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
    assert analysis.summary["canonical_entity"] == "cutting_sheet"
    assert analysis.summary["stock_source"] is True
    assert analysis.summary["debit_lines"] == 2
    assert analysis.summary["total_quantity"] == 53
    assert [record["reference"] for record in analysis.records] == ["7007", "70501"]


def test_proges_fabrication_pdf_is_detected_and_parsed_as_cutting(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "fiche-proges-anonymisee.pdf"
    path.write_bytes(b"%PDF-test")
    text = """Logiciel PROGES ©25
FICHE DE FABRICATION
Affaire : PVC-ANON-003
LOT : REPERE : F03
Référence Désignation Coloris Qté Débit Coupe
K6
76180---2 Dormant anonymisé WSWS 2 1645,0 45.0/ 45.0 u T
QU
CALE3 Cale anonymisée B 4 pièce
"""
    monkeypatch.setattr(
        "backend.services.technical_document_analysis._document_text",
        lambda _path: text,
    )
    monkeypatch.setattr(
        "scripts.import_workshop_debits.extract_pdf_text",
        lambda _path: text,
    )

    analysis = analyze_technical_document(
        path,
        "CUTTING",
        "OTHER",
        "PVC-ANON-003",
    )

    assert analysis.status == "PARSED"
    assert analysis.detected_document_type == "CUTTING"
    assert analysis.detected_source_system == "PROGES"
    assert analysis.detected_project_reference == "PVC-ANON-003"
    assert analysis.summary["raw_records"] == 2
    assert analysis.summary["debit_lines"] == 2
    assert analysis.records[0]["cut_left_deg"] == 45
    assert analysis.records[0]["cut_right_deg"] == 45


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
    assert analysis.summary["canonical_entity"] == "fabrication_sheet"
    assert analysis.summary["stock_source"] is False
    assert "cutting_sheet" in analysis.summary["forbidden_confusions"]
    assert analysis.records == []


def test_orgadata_fabrication_pdf_extracts_previewable_workshop_data(tmp_path, monkeypatch):
    path = tmp_path / "Bon atelier ORGADATA.pdf"
    path.write_bytes(b"%PDF-test")
    text = """RECETTE LOGICIELLE - DOCUMENT FICTIF - NE PAS FABRIQUER
ORGADATA LogiKal - Bon d'atelier
Affaire: ALU-RECETTE-2026-001
BON D'ATELIER
Position Systeme Type Dimensions Finition Quantite
CH1 Cortizo COR 70 INDUSTRIAL Fixe 900 x 2100 mm RAL 7016 mat 1
Vitrage: 44.2 clair / 16 argon / 4 faible emissivite
Accessoires: Paumelles invisibles, Poignee noire
Remarques: Controle equerrage avant vitrage
PF1 Cortizo COR 70 INDUSTRIAL Porte-fenetre 1200 x 2380 mm RAL 7016 mat 1
"""
    monkeypatch.setattr(
        "backend.services.technical_document_analysis._document_text",
        lambda _path: text,
    )

    analysis = analyze_technical_document(
        path,
        "FABRICATION",
        "ORGADATA",
        "ALU-RECETTE-2026-001",
    )

    assert analysis.status == "PARSED"
    assert analysis.detected_document_type == "FABRICATION"
    assert analysis.detected_source_system == "ORGADATA"
    assert analysis.summary["canonical_entity"] == "fabrication_sheet"
    assert analysis.summary["stock_source"] is False
    assert analysis.summary["fabrication_lines"] == 2
    assert analysis.summary["opening_count"] == 2
    assert analysis.summary["systems"] == {"Cortizo COR 70 INDUSTRIAL": 2}
    assert analysis.summary["with_glazing"] == 1
    assert analysis.summary["with_accessories"] == 1
    assert [record["position"] for record in analysis.records] == ["CH1", "PF1"]
    assert analysis.records[0]["glazing"] == "44.2 clair / 16 argon / 4 faible emissivite"


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

from pathlib import Path

from scripts.import_workshop_debits import (
    build_summary,
    consolidate_records,
    detect_project_reference,
    is_cortizo_order_text,
    is_orgadata_fabrication_text,
    is_proges_fabrication_text,
    parse_cortizo_order_pdf,
    parse_orgadata_fabrication_pdf,
    parse_orgadata_optimized_pdf,
    parse_proges_fabrication_pdf,
    parse_file,
    parse_progers_txt,
)


def test_parse_progers_txt_extracts_semicolon_debits(tmp_path):
    path = tmp_path / "SEPVER.TXT"
    path.write_text(
        """MMG
SEPALUMIC GAMME BASE
VER DIMASCIO
22-04-2026

RAL 8017S Satiné (+25%);7007;BAVETTE DE FAITAGE;3;barre  6,50
Brut ( Q-U );70501;JOINT DE BAVETTE;50;ml
RAL 8017S Satiné (+25%);70305;EMBOUT DE FAITAGE;4;unité
""",
        encoding="latin-1",
    )

    records, issues = parse_progers_txt(path, path.read_text(encoding="latin-1"))
    summary = build_summary(records, issues)

    assert not issues
    assert summary["raw_records"] == 3
    assert summary["unique_references"] == 3
    assert summary["suppliers"] == {"SEPALUMIC": 3}
    assert summary["units"] == {"barre": 1, "ml": 1, "unité": 1}
    assert records[0].reference == "7007"
    assert records[0].quantity == 3
    assert records[0].length_mm == 6500
    assert detect_project_reference(path.read_text(encoding="latin-1")) == "VER DIMASCIO"


def test_parse_proges_fabrication_pdf_extracts_profiles_and_accessories(tmp_path):
    path = tmp_path / "PVC-ANON-001.pdf"
    text = """29/07/2026 Logiciel PROGES ©25 page N° 1
Utilisation : MMG
FICHE DE FABRICATION
Affaire : PVC-ANON-001 PVC-ANON-001
Client : CLIENT ANONYMISE
LOT : REPERE : F01
Référence Désignation Coloris Qté Débit Coupe
K6
HFFO HAUTEUR fond de feuillure ouvr B 1 1930,0 90.0/ 90.0 M
76177---2 Dormant réno anonymisé WSWS 2 1455,0 45.0/ 45.0 u T
76281---2 Ouvrant anonymisé WSWS 4 689,0 45.0/ 45.0 u T
QU
CALE3 Cale de vitrage B 8 pièce
RX
POIG7-15 Poignée anonymisée B 1 unité
"""

    assert is_proges_fabrication_text(text)
    records, issues = parse_proges_fabrication_pdf(path, text)

    assert not issues
    assert [record.reference for record in records] == [
        "76177---2",
        "76281---2",
        "CALE3",
        "POIG7-15",
    ]
    assert all(record.project_reference == "PVC-ANON-001" for record in records)
    assert records[0].supplier == "KOMMERLING"
    assert records[0].quantity == 2
    assert records[0].length_mm == 1455
    assert records[0].cut_left_deg == 45
    assert records[0].cut_right_deg == 45
    assert records[0].cut_orientation == "u T"
    assert records[0].position == "F01"
    assert records[2].supplier == "QUINCAILLERIE"
    assert records[2].unit == "pce"
    assert records[3].supplier == "ROTO"


def test_parse_file_routes_proges_fabrication_pdf_automatically(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "fiche-proges-anonymisee.pdf"
    path.write_bytes(b"%PDF-test")
    text = """Logiciel PROGES ©25
FICHE DE FABRICATION
Affaire : PVC-ANON-002
LOT : REPERE : F02
Référence Désignation Coloris Qté Débit Coupe
K6
76180---2 Dormant anonymisé WSWS 2 1845,0 45.0/ 45.0 u M
"""
    monkeypatch.setattr(
        "scripts.import_workshop_debits.extract_pdf_text",
        lambda _path: text,
    )

    records, issues = parse_file(path)

    assert not issues
    assert len(records) == 1
    assert records[0].reference == "76180---2"


def test_parse_orgadata_optimized_pdf_text_extracts_bar_requirements(tmp_path):
    path = tmp_path / "Optimisation.pdf"
    text = """Débit optimisé                   Date: 27/03/2026 / 16:27
                                         Affaire: MMG26020068NC
                      Cortizo 2000       Ouvrant coulissant vitrage double
                                         Trait. surface: L. Spécial 3 9007
                      4 Pce á 6 500 mm   Largeur: 26,0 mm / Hauteur: 66,0
        Quantité         Débit     Longueur    Coupe    Position
                      Cortizo 2022       Dormant fenêtre de 45 mm
                                         Trait. surface: L. Spécial 3 9007
                      2 Pce á 6 500 mm   Largeur: 45,0 mm / Hauteur: 47,0
"""

    records, issues = parse_orgadata_optimized_pdf(path, text)
    consolidated = consolidate_records(records)

    assert not issues
    assert len(consolidated) == 2
    assert consolidated[0].supplier == "CORTIZO"
    assert consolidated[0].reference == "2000"
    assert consolidated[0].quantity == 4
    assert consolidated[0].project_reference == "MMG26020068NC"
    assert consolidated[1].reference == "2022"
    assert consolidated[1].length_mm == 6500


def test_parse_orgadata_fabrication_pdf_extracts_workshop_openings(tmp_path):
    path = tmp_path / "bon-atelier-orgadata-anonymise.pdf"
    text = """ORGADATA LogiKal - Bon d'atelier
Affaire: ALU-RECETTE-2026-001
BON D'ATELIER
Position Systeme Type Dimensions Finition Quantite
CH1 Cortizo COR 70 INDUSTRIAL Fixe 900 x 2100 mm RAL 7016 mat 1
Vitrage: 44.2 clair / 16 argon / 4 faible emissivite
Accessoires: Paumelles invisibles, Poignee noire
Remarques: Controle equerrage avant vitrage
PF1 Cortizo COR 70 INDUSTRIAL Porte-fenetre 1200 x 2380 mm RAL 7016 mat 1
"""

    assert is_orgadata_fabrication_text(text)
    records, issues = parse_orgadata_fabrication_pdf(path, text)

    assert not issues
    assert len(records) == 2
    assert records[0]["position"] == "CH1"
    assert records[0]["system"] == "Cortizo COR 70 INDUSTRIAL"
    assert records[0]["opening_type"] == "Fixe"
    assert records[0]["width_mm"] == 900
    assert records[0]["height_mm"] == 2100
    assert records[0]["finish"] == "RAL 7016 mat"
    assert records[0]["quantity"] == 1
    assert records[0]["material"] == "ALU"
    assert records[0]["glazing"] == "44.2 clair / 16 argon / 4 faible emissivite"
    assert records[0]["accessories"] == ["Paumelles invisibles", "Poignee noire"]
    assert records[0]["remarks"] == "Controle equerrage avant vitrage"
    assert records[1]["position"] == "PF1"
    assert records[1]["opening_type"] == "Porte-fenetre"


def test_parse_cortizo_order_uses_required_quantity_not_purchase_pack(tmp_path):
    path = tmp_path / "commande-cortizo-anonymisee.pdf"
    text = """--- PAGE 1 ---
AFFAIRE N°MMG26070001V2modifiée - CLIENT TEST
Commande
Nom affaire: ALIAS LIBRE
Ferrure
Croquis Quantité / Numéro Description Teinte Prix Total
        Unité [EUR] [EUR]
        3 pce (3) 123456 Poignée de test Blanc 2,00 6,00
Accessoires
Croquis Quantité / Numéro Description Teinte Prix Total
        Unité [EUR] [EUR]
        (Nécessaire)
        2 UV á 25 pce 654321 Équerre de test 0,50 25,00
        (40)
        1 UV á 1 000 800001 Vis de test Noir 0,02 20,00
        pce (80)
Somme: 51,00
"""

    assert is_cortizo_order_text(text)
    records, issues = parse_cortizo_order_pdf(path, text)

    assert not issues
    assert [record.reference for record in records] == [
        "123456",
        "654321",
        "800001",
    ]
    assert [record.quantity for record in records] == [3, 40, 80]
    assert all(record.unit == "pce" for record in records)
    assert all(
        record.project_reference == "MMG26070001V2modifiée" for record in records
    )
    assert records[0].color == "BLANC"
    assert records[2].color == "NOIR"
    assert records[0].position == "Ferrure"
    assert records[1].position == "Accessoires"


def test_parse_cortizo_order_does_not_guess_missing_required_quantity(tmp_path):
    path = tmp_path / "commande-cortizo-incomplete.pdf"
    text = """AFFAIRE N°MMG26070002 - CLIENT TEST
Commande
Croquis Quantité / Numéro Description Teinte Prix Total
1 UV á 50 pce 654321 Article sans besoin atelier
"""

    records, issues = parse_cortizo_order_pdf(path, text)

    assert records == []
    assert [issue.code for issue in issues] == [
        "missing_required_quantity",
        "no_cortizo_requirements",
    ]

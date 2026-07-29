from pathlib import Path

from scripts.import_workshop_debits import (
    build_summary,
    consolidate_records,
    detect_project_reference,
    is_cortizo_order_text,
    parse_cortizo_order_pdf,
    parse_orgadata_optimized_pdf,
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
    assert summary["suppliers"] == {"SEPALUMIC": 3}
    assert summary["units"] == {"barre": 1, "ml": 1, "unité": 1}
    assert records[0].reference == "7007"
    assert records[0].quantity == 3
    assert records[0].length_mm == 6500
    assert detect_project_reference(path.read_text(encoding="latin-1")) == "VER DIMASCIO"


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

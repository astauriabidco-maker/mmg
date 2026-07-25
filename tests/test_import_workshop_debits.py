from pathlib import Path

from scripts.import_workshop_debits import (
    build_summary,
    consolidate_records,
    detect_project_reference,
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

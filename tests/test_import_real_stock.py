from pathlib import Path

from openpyxl import Workbook

from scripts.import_real_stock import build_issue_report_rows, build_summary, consolidate_records, parse_workbook


def write_stock_workbook(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Feuil1"
    sheet.append(["CORTIZO", None, None, None, None, None, "GEZE"])
    sheet.append([])
    sheet.append(
        [
            "Réf",
            "Nom de l'accessoire",
            "Quant",
            "Gamme",
            "iIlustration",
            None,
            "Réf",
            "Nom de l'accessoire",
            "Quant",
            "Gamme",
            "iIlustration",
        ]
    )
    sheet.append([])
    sheet.append(["A-001", "Equerre", 3, "COR 70", None, None, "/030377", "Compas", 5, "OL 90", None])
    sheet.append(["A-001", "Equerre", 2, "COR 70", None, None, None, "Sans ref", 1, "OL 90", None])
    sheet.append(["A-002", "Poignee", None, "COR 2000", None, None, "/074509", "Compas noir", "bad", "OL 90", None])
    workbook.save(path)


def write_conflicting_stock_workbook(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Feuil1"
    sheet.append(["CORTIZO"])
    sheet.append([])
    sheet.append(["Réf", "Nom de l'accessoire", "Quant", "Gamme", "iIlustration"])
    sheet.append([])
    sheet.append(["A-001", "Equerre", 3, "COR 70", None])
    sheet.append(["A-001", "Equerre autre", 2, "COR 70", None])
    workbook.save(path)


def test_parse_workbook_detects_supplier_blocks_and_issues(tmp_path):
    path = tmp_path / "stock.xlsx"
    write_stock_workbook(path)

    records, issues = parse_workbook(path)
    summary = build_summary(records, issues)

    assert summary["raw_records"] == 5
    assert summary["importable_records"] == 4
    assert summary["suppliers"] == {"CORTIZO": 2, "GEZE": 2}
    assert summary["issues"]["duplicate_quantity_disagreement"] == 1
    assert summary["issues"]["missing_or_invalid_quantity"] == 2
    assert summary["issues"]["missing_reference"] == 1


def test_consolidate_records_does_not_sum_duplicate_supplier_references(tmp_path):
    path = tmp_path / "stock.xlsx"
    write_stock_workbook(path)

    records, _issues = parse_workbook(path)
    consolidated = consolidate_records(records)
    cortizo_a001 = next(record for record in consolidated if record.supplier == "CORTIZO" and record.reference == "A-001")

    assert cortizo_a001.quantity == 3
    assert cortizo_a001.designation == "Equerre"


def test_consolidate_records_quarantines_conflicting_duplicate_references(tmp_path):
    path = tmp_path / "stock.xlsx"
    write_conflicting_stock_workbook(path)

    records, issues = parse_workbook(path)
    consolidated = consolidate_records(records)

    assert not any(record.supplier == "CORTIZO" and record.reference == "A-001" for record in consolidated)
    assert any(issue.code == "duplicate_reference_conflict" for issue in issues)


def test_build_issue_report_expands_conflicting_duplicate_rows(tmp_path):
    path = tmp_path / "stock.xlsx"
    write_conflicting_stock_workbook(path)

    records, issues = parse_workbook(path)
    report_rows = build_issue_report_rows(records, issues)
    conflict_rows = [row for row in report_rows if row["code"] == "duplicate_reference_conflict"]

    assert len(conflict_rows) == 2
    assert {row["designation"] for row in conflict_rows} == {"Equerre", "Equerre autre"}
    assert all(row["decision"] == "Arbitrer la bonne désignation puis réimporter." for row in conflict_rows)

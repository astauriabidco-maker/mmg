#!/usr/bin/env python3
"""Import a real multi-supplier stock workbook into MMG.

Default mode is a dry-run preview. Use --apply to write products, variants,
stock quants and initial inventory moves.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.database import SessionLocal
from backend import models


EXPECTED_HEADERS = ["Réf", "Nom de l'accessoire", "Quant", "Gamme", "iIlustration"]


@dataclass(frozen=True)
class StockRecord:
    row: int
    supplier: str
    reference: str
    designation: str
    quantity: float | None
    gamme: str
    unit: str = "pce"
    material_type: str = "ACCESSOIRE"
    product_type: str = "stockable"


@dataclass(frozen=True)
class StockIssue:
    severity: str
    code: str
    row: int | None
    supplier: str | None
    reference: str | None
    message: str


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\xa0", " ").split()).strip()


def parse_quantity(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = value.replace(",", ".").strip()
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def iter_supplier_blocks(rows: list[tuple[Any, ...]], max_column: int) -> list[tuple[int, str]]:
    blocks: list[tuple[int, str]] = []
    current_supplier = ""
    for start in range(0, max_column, 6):
        supplier = clean_text(rows[0][start] if start < len(rows[0]) else None)
        if supplier:
            current_supplier = supplier

        headers = [clean_text(value) for value in rows[2][start : start + 5]]
        if current_supplier and headers[:5] == EXPECTED_HEADERS:
            blocks.append((start, current_supplier))
    return blocks


def parse_workbook(path: Path) -> tuple[list[StockRecord], list[StockIssue]]:
    workbook = load_workbook(path, data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    issues: list[StockIssue] = []

    if len(rows) < 5:
        return [], [
            StockIssue("error", "empty_workbook", None, None, None, "Le classeur ne contient pas assez de lignes.")
        ]

    blocks = iter_supplier_blocks(rows, sheet.max_column)
    if not blocks:
        return [], [
            StockIssue(
                "error",
                "missing_blocks",
                None,
                None,
                None,
                "Aucun bloc fournisseur Réf/Nom/Quant/Gamme/Illustration reconnu.",
            )
        ]

    records: list[StockRecord] = []
    for start, supplier in blocks:
        for row_number, row in enumerate(rows[4:], start=5):
            values = list(row[start : start + 5])
            values += [None] * (5 - len(values))
            ref, designation, quantity_raw, gamme, _illustration = values
            if all(value is None for value in values):
                continue

            reference = clean_text(ref)
            name = clean_text(designation)
            quantity = parse_quantity(quantity_raw)
            gamme_text = clean_text(gamme)

            if not reference:
                issues.append(
                    StockIssue(
                        "error",
                        "missing_reference",
                        row_number,
                        supplier,
                        None,
                        "Ligne ignorée: référence manquante.",
                    )
                )
                continue
            if not name:
                issues.append(
                    StockIssue(
                        "warning",
                        "missing_designation",
                        row_number,
                        supplier,
                        reference,
                        "Désignation vide; le nom produit utilisera la référence.",
                    )
                )
                name = reference
            if quantity is None:
                issues.append(
                    StockIssue(
                        "warning",
                        "missing_or_invalid_quantity",
                        row_number,
                        supplier,
                        reference,
                        f"Quantité vide ou invalide ({quantity_raw!r}); importée à 0.",
                    )
                )
                quantity = 0.0

            records.append(
                StockRecord(
                    row=row_number,
                    supplier=supplier,
                    reference=reference,
                    designation=name,
                    quantity=quantity,
                    gamme=gamme_text,
                )
            )

    duplicate_counts = Counter((record.supplier, record.reference) for record in records)
    for (supplier, reference), count in duplicate_counts.items():
        if count > 1:
            issues.append(
                StockIssue(
                    "warning",
                    "duplicate_supplier_reference",
                    None,
                    supplier,
                    reference,
                    f"Référence présente {count} fois pour ce fournisseur; les quantités seront cumulées.",
                )
            )

    return records, issues


def consolidate_records(records: list[StockRecord]) -> list[StockRecord]:
    consolidated: dict[tuple[str, str], StockRecord] = {}
    for record in records:
        key = (record.supplier, record.reference)
        existing = consolidated.get(key)
        if not existing:
            consolidated[key] = record
            continue

        consolidated[key] = StockRecord(
            row=existing.row,
            supplier=existing.supplier,
            reference=existing.reference,
            designation=existing.designation or record.designation,
            quantity=(existing.quantity or 0) + (record.quantity or 0),
            gamme=existing.gamme if record.gamme in existing.gamme else clean_text(f"{existing.gamme} {record.gamme}"),
            unit=existing.unit,
            material_type=existing.material_type,
            product_type=existing.product_type,
        )
    return list(consolidated.values())


def build_summary(records: list[StockRecord], issues: list[StockIssue]) -> dict[str, Any]:
    consolidated = consolidate_records(records)
    supplier_counts = Counter(record.supplier for record in consolidated)
    issue_counts = Counter(issue.code for issue in issues)
    positive_count = sum(1 for record in consolidated if (record.quantity or 0) > 0)
    zero_count = sum(1 for record in consolidated if (record.quantity or 0) == 0)
    return {
        "raw_records": len(records),
        "importable_records": len(consolidated),
        "positive_quantity_records": positive_count,
        "zero_quantity_records": zero_count,
        "suppliers": dict(sorted(supplier_counts.items())),
        "issues": dict(sorted(issue_counts.items())),
    }


def get_or_create_location(db, name: str) -> models.StockLocation:
    location = db.query(models.StockLocation).filter_by(name=name, usage="internal").first()
    if location:
        return location

    location = models.StockLocation(name=name, usage="internal", is_active=True)
    db.add(location)
    db.flush()
    return location


def import_records(records: list[StockRecord], location_name: str, dry_run: bool) -> dict[str, int]:
    consolidated = consolidate_records(records)
    stats = {
        "created_products": 0,
        "updated_products": 0,
        "created_variants": 0,
        "updated_variants": 0,
        "created_quants": 0,
        "updated_quants": 0,
        "created_moves": 0,
    }

    if dry_run:
        return stats

    db = SessionLocal()
    try:
        location = get_or_create_location(db, location_name)
        now_ref = datetime.utcnow().strftime("%Y%m%d%H%M%S")

        for record in consolidated:
            product_reference = f"{record.supplier}:{record.reference}"
            variant_reference = product_reference

            product = db.query(models.Product).filter_by(reference_base=product_reference).first()
            if not product:
                product = models.Product(
                    reference_base=product_reference,
                    name=record.designation,
                    material_type=record.material_type,
                    unit=record.unit,
                    supplier=record.supplier,
                    product_type=record.product_type,
                    compatible_series=record.gamme,
                )
                db.add(product)
                db.flush()
                stats["created_products"] += 1
            else:
                product.name = record.designation or product.name
                product.material_type = record.material_type
                product.unit = record.unit
                product.supplier = record.supplier
                product.product_type = record.product_type
                product.compatible_series = record.gamme or product.compatible_series
                stats["updated_products"] += 1

            variant = db.query(models.ProductVariant).filter_by(reference=variant_reference).first()
            if not variant:
                variant = models.ProductVariant(
                    product_id=product.id,
                    reference=variant_reference,
                    supplier_reference=record.reference,
                    quantity_in_stock=record.quantity or 0,
                    min_threshold=0,
                    location=location_name,
                )
                db.add(variant)
                db.flush()
                stats["created_variants"] += 1
            else:
                variant.product_id = product.id
                variant.supplier_reference = record.reference
                variant.quantity_in_stock = record.quantity or 0
                variant.location = location_name
                stats["updated_variants"] += 1

            quant = db.query(models.StockQuant).filter_by(variant_id=variant.id, location_id=location.id).first()
            previous_qty = quant.quantity if quant else 0
            if not quant:
                quant = models.StockQuant(variant_id=variant.id, location_id=location.id, quantity=record.quantity or 0)
                db.add(quant)
                stats["created_quants"] += 1
            else:
                quant.quantity = record.quantity or 0
                stats["updated_quants"] += 1

            if previous_qty != (record.quantity or 0):
                db.add(
                    models.StockMove(
                        reference=f"INIT-STOCK-{now_ref}",
                        variant_id=variant.id,
                        location_dest_id=location.id,
                        quantity=(record.quantity or 0) - previous_qty,
                        state="done",
                        notes=f"Import stock réel fournisseur {record.supplier}",
                        author="Import stock réel",
                    )
                )
                stats["created_moves"] += 1

        db.commit()
        return stats
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def write_json(path: Path, records: list[StockRecord], issues: list[StockIssue], summary: dict[str, Any]) -> None:
    payload = {
        "summary": summary,
        "issues": [asdict(issue) for issue in issues],
        "records": [asdict(record) for record in consolidate_records(records)],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prévisualise ou importe le stock réel Excel multi-fournisseurs MMG.")
    parser.add_argument("file", type=Path, help="Fichier .xlsx de stock réel.")
    parser.add_argument("--apply", action="store_true", help="Importe réellement en base. Sans cette option: prévisualisation.")
    parser.add_argument("--location", default="WH/Stock", help="Emplacement interne cible pour les quantités.")
    parser.add_argument("--json-out", type=Path, help="Écrit la prévisualisation complète en JSON.")
    parser.add_argument("--fail-on-errors", action="store_true", help="Retourne 1 si des erreurs bloquantes sont détectées.")
    parser.add_argument("--allow-errors", action="store_true", help="Autorise --apply malgré des erreurs bloquantes ignorées.")
    args = parser.parse_args()

    if not args.file.exists():
        print(f"FAIL: fichier introuvable: {args.file}", file=sys.stderr)
        return 1

    records, issues = parse_workbook(args.file)
    summary = build_summary(records, issues)
    blocking_errors = [issue for issue in issues if issue.severity == "error"]

    print("# Prévisualisation import stock réel")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    for issue in issues[:30]:
        location = f"ligne {issue.row}" if issue.row else "global"
        print(f"{issue.severity.upper()}: {issue.code} ({location}, {issue.supplier or '-'}/{issue.reference or '-'}) - {issue.message}")
    if len(issues) > 30:
        print(f"INFO: {len(issues) - 30} autres alertes non affichées. Utiliser --json-out pour le détail.")

    if args.json_out:
        write_json(args.json_out, records, issues, summary)
        print(f"JSON: {args.json_out}")

    if args.fail_on_errors and blocking_errors:
        return 1

    if args.apply and blocking_errors and not args.allow_errors:
        print("FAIL: erreurs bloquantes détectées. Corriger le fichier ou relancer avec --allow-errors.", file=sys.stderr)
        return 1

    stats = import_records(records, args.location, dry_run=not args.apply)
    if args.apply:
        print("# Import appliqué")
    else:
        print("# Dry-run: aucune écriture en base")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

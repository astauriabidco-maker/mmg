#!/usr/bin/env python3
"""Preview or apply workshop stock debits from third-party production files.

Supported first-pass formats:
- Progers/Proges semicolon TXT purchase/debit files.
- Orgadata/Logikal optimized cutting PDF files.

Default mode is a dry-run preview. Use --apply to move stock from WH/Stock to
Production Ateliers.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pdfplumber
from sqlalchemy import or_

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend import models
from backend.database import SessionLocal
from backend.services.stock_service import InventoryService


logging.getLogger("pdfminer").setLevel(logging.ERROR)

SUPPLIER_ALIASES = {
    "CORTIZO": "CORTIZO",
    "SEPALUMIC": "SEPALUMIC",
    "SEPALUMIC GAMME BASE": "SEPALUMIC",
    "TECHNAL": "TECHNAL/HYDRO",
    "HYDRO": "TECHNAL/HYDRO",
}


@dataclass(frozen=True)
class DebitRecord:
    source: str
    row: int | None
    supplier: str
    reference: str
    designation: str
    quantity: float
    unit: str
    project_reference: str | None = None
    color: str | None = None
    length_mm: float | None = None
    position: str | None = None


@dataclass(frozen=True)
class DebitIssue:
    severity: str
    code: str
    source: str
    row: int | None
    reference: str | None
    message: str


@dataclass(frozen=True)
class StockMatch:
    source: str
    reference: str
    supplier: str
    requested_quantity: float
    unit: str
    variant_reference: str | None
    product_name: str | None
    available_quantity: float
    missing_quantity: float
    status: str


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\xa0", " ").split()).strip()


def normalize_supplier(value: str) -> str:
    raw = clean_text(value).upper()
    for key, normalized in SUPPLIER_ALIASES.items():
        if key in raw:
            return normalized
    return raw or "INCONNU"


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    text = clean_text(value).replace(" ", "").replace(",", ".")
    if not text or text == "/":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def read_text_file(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "latin-1", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


def extract_pdf_text(path: Path) -> str:
    pages: list[str] = []
    with pdfplumber.open(path) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text(x_tolerance=1, y_tolerance=3, layout=True) or ""
            pages.append(f"--- PAGE {index} ---\n{text}")
    return "\n".join(pages)


def detect_project_reference(text: str) -> str | None:
    patterns = [
        r"Affaire:\s*([A-Z0-9_-]+)",
        r"Référence Commande\s*:\s*([^\n\r]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return clean_text(match.group(1))
    lines = [clean_text(line) for line in text.splitlines()]
    for index, line in enumerate(lines):
        if re.fullmatch(r"\d{2}[-/]\d{2}[-/]\d{4}", line) and index:
            for candidate in reversed(lines[:index]):
                if candidate and "GAMME" not in candidate.upper():
                    return candidate
    return None


def detect_progers_supplier(text: str) -> str:
    for line in text.splitlines():
        line = clean_text(line)
        if "GAMME" in line or "SEPALUMIC" in line:
            return normalize_supplier(line)
    return "INCONNU"


def parse_progers_txt(path: Path, text: str) -> tuple[list[DebitRecord], list[DebitIssue]]:
    supplier = detect_progers_supplier(text)
    project_reference = detect_project_reference(text)
    records: list[DebitRecord] = []
    issues: list[DebitIssue] = []

    reader = csv.reader(io.StringIO(text), delimiter=";")
    for row_number, columns in enumerate(reader, start=1):
        if len(columns) < 5:
            continue

        color, reference, designation, quantity_raw, unit_raw = [clean_text(value) for value in columns[:5]]
        reference = reference.strip()
        if not reference or not re.search(r"\d", reference):
            continue

        quantity = parse_number(quantity_raw)
        if quantity is None:
            issues.append(
                DebitIssue(
                    "warning",
                    "invalid_quantity",
                    path.name,
                    row_number,
                    reference,
                    f"Quantité invalide ({quantity_raw!r}); ligne ignorée.",
                )
            )
            continue

        unit_text = unit_raw.lower()
        unit = "barre" if unit_text.startswith("barre") else unit_text or "pce"
        length_match = re.search(r"([0-9]+(?:[,.][0-9]+)?)", unit_raw)
        length_mm = None
        if unit == "barre" and length_match:
            length_mm = (parse_number(length_match.group(1)) or 0) * 1000

        records.append(
            DebitRecord(
                source=path.name,
                row=row_number,
                supplier=supplier,
                reference=reference,
                designation=designation or reference,
                quantity=quantity,
                unit=unit,
                project_reference=project_reference,
                color=color or None,
                length_mm=length_mm,
            )
        )

    if not records:
        issues.append(DebitIssue("error", "no_records", path.name, None, None, "Aucune ligne Progers exploitable."))
    return records, issues


ORGADATA_SECTION_RE = re.compile(
    r"^\s*(Cortizo|Technal|Hydro|Sepalumic)\s+([A-Za-z0-9./_-]+)\s+(.+?)\s*$",
    re.IGNORECASE,
)
ORGADATA_BAR_RE = re.compile(r"^\s*([0-9]+)\s+Pce\s+[àaá]\s+([0-9 ]+(?:[,.][0-9]+)?)\s*mm", re.IGNORECASE)


def parse_orgadata_optimized_pdf(path: Path, text: str) -> tuple[list[DebitRecord], list[DebitIssue]]:
    project_reference = detect_project_reference(text)
    records: list[DebitRecord] = []
    issues: list[DebitIssue] = []
    current: dict[str, str] | None = None

    for row_number, line in enumerate(text.splitlines(), start=1):
        section = ORGADATA_SECTION_RE.match(line)
        if section and not any(skip in line.lower() for skip in ["quantité", "numéro", "chutes restantes"]):
            current = {
                "supplier": normalize_supplier(section.group(1)),
                "reference": clean_text(section.group(2)),
                "designation": clean_text(section.group(3)).rstrip(", 0"),
            }
            continue

        bar_match = ORGADATA_BAR_RE.match(line)
        if bar_match and current:
            quantity = parse_number(bar_match.group(1)) or 0
            length_mm = parse_number(bar_match.group(2))
            records.append(
                DebitRecord(
                    source=path.name,
                    row=row_number,
                    supplier=current["supplier"],
                    reference=current["reference"],
                    designation=current["designation"] or current["reference"],
                    quantity=quantity,
                    unit="barre",
                    project_reference=project_reference,
                    length_mm=length_mm,
                )
            )
            current = None

    if not records:
        issues.append(
            DebitIssue(
                "error",
                "no_orgadata_bars",
                path.name,
                None,
                None,
                "Aucun bloc Orgadata 'N Pce à longueur mm' reconnu.",
            )
        )
    return records, issues


def parse_file(path: Path) -> tuple[list[DebitRecord], list[DebitIssue]]:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return parse_progers_txt(path, read_text_file(path))
    if suffix == ".pdf":
        text = extract_pdf_text(path)
        if "Débit optimisé" in text:
            return parse_orgadata_optimized_pdf(path, text)
        return [], [
            DebitIssue(
                "info",
                "unsupported_pdf",
                path.name,
                None,
                None,
                "PDF lu mais non débité automatiquement; utiliser le Débit optimisé ou le TXT fournisseur.",
            )
        ]
    return [], [DebitIssue("error", "unsupported_file", path.name, None, None, f"Format non supporté: {suffix}")]


def consolidate_records(records: list[DebitRecord]) -> list[DebitRecord]:
    consolidated: dict[tuple[str, str, str, str, float | None], DebitRecord] = {}
    for record in records:
        key = (record.source, record.supplier, record.reference, record.unit, record.length_mm)
        existing = consolidated.get(key)
        if not existing:
            consolidated[key] = record
            continue

        consolidated[key] = DebitRecord(
            source=existing.source,
            row=existing.row,
            supplier=existing.supplier,
            reference=existing.reference,
            designation=existing.designation,
            quantity=existing.quantity + record.quantity,
            unit=existing.unit,
            project_reference=existing.project_reference or record.project_reference,
            color=existing.color or record.color,
            length_mm=existing.length_mm,
            position=existing.position,
        )
    return list(consolidated.values())


def build_summary(records: list[DebitRecord], issues: list[DebitIssue]) -> dict[str, Any]:
    consolidated = consolidate_records(records)
    return {
        "raw_records": len(records),
        "debit_lines": len(consolidated),
        "total_quantity": sum(record.quantity for record in consolidated),
        "suppliers": dict(sorted(Counter(record.supplier for record in consolidated).items())),
        "units": dict(sorted(Counter(record.unit for record in consolidated).items())),
        "sources": dict(sorted(Counter(record.source for record in consolidated).items())),
        "issues": dict(sorted(Counter(issue.code for issue in issues).items())),
    }


def get_or_create_location(db, name: str, usage: str) -> models.StockLocation:
    location = db.query(models.StockLocation).filter_by(name=name, usage=usage).first()
    if location:
        return location
    location = models.StockLocation(name=name, usage=usage, is_active=True)
    db.add(location)
    db.flush()
    return location


def find_variant(db, record: DebitRecord) -> models.ProductVariant | None:
    supplier_prefixed = f"{record.supplier}:{record.reference}"
    variant = (
        db.query(models.ProductVariant)
        .join(models.Product, models.ProductVariant.product_id == models.Product.id)
        .filter(
            or_(
                models.ProductVariant.reference == supplier_prefixed,
                models.ProductVariant.reference == record.reference,
                models.ProductVariant.barcode == record.reference,
                models.ProductVariant.supplier_reference == record.reference,
            )
        )
        .order_by((models.Product.supplier == record.supplier).desc())
        .first()
    )
    return variant


def preview_stock(records: list[DebitRecord], source_location: str) -> list[StockMatch]:
    db = SessionLocal()
    try:
        source = db.query(models.StockLocation).filter_by(name=source_location, usage="internal").first()
        matches: list[StockMatch] = []
        for record in consolidate_records(records):
            variant = find_variant(db, record)
            available = 0.0
            if variant and source:
                quant = db.query(models.StockQuant).filter_by(variant_id=variant.id, location_id=source.id).first()
                available = float(quant.quantity if quant else 0)
            missing = max(record.quantity - available, 0)
            if not variant:
                status = "not_found"
            elif missing > 0:
                status = "shortage"
            else:
                status = "ok"
            matches.append(
                StockMatch(
                    source=record.source,
                    reference=record.reference,
                    supplier=record.supplier,
                    requested_quantity=record.quantity,
                    unit=record.unit,
                    variant_reference=variant.reference if variant else None,
                    product_name=variant.product.name if variant and variant.product else None,
                    available_quantity=available,
                    missing_quantity=missing,
                    status=status,
                )
            )
        return matches
    finally:
        db.close()


def apply_debits(records: list[DebitRecord], source_location: str, dest_location: str, allow_shortage: bool) -> dict[str, int]:
    stats = {"created_moves": 0, "updated_source_quants": 0, "updated_dest_quants": 0, "skipped_missing": 0}
    db = SessionLocal()
    try:
        source = get_or_create_location(db, source_location, "internal")
        dest = get_or_create_location(db, dest_location, "production")
        now_ref = datetime.utcnow().strftime("%Y%m%d%H%M%S")

        for record in consolidate_records(records):
            variant = find_variant(db, record)
            if not variant:
                stats["skipped_missing"] += 1
                continue

            try:
                InventoryService.move_stock(
                    db,
                    variant_id=variant.id,
                    source_location_id=source.id,
                    dest_location_id=dest.id,
                    quantity=record.quantity,
                    reference=f"DEBIT-ATELIER-{now_ref}",
                    notes=f"Débit atelier {record.source} - {record.project_reference or 'sans affaire'}",
                    author="Import débit atelier",
                    source_screen="script.import_workshop_debits",
                    document_type="workshop_debit_file",
                    document_reference=record.project_reference or record.source,
                    business_reason="Import débit atelier",
                    allow_negative_source=allow_shortage,
                )
            except ValueError as exc:
                raise RuntimeError(f"Stock insuffisant pour {variant.reference}: {exc}") from exc
            stats["updated_source_quants"] += 1
            stats["updated_dest_quants"] += 1
            stats["created_moves"] += 1

        db.commit()
        return stats
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def write_json(path: Path, records: list[DebitRecord], issues: list[DebitIssue], summary: dict[str, Any], matches: list[StockMatch]) -> None:
    payload = {
        "summary": summary,
        "issues": [asdict(issue) for issue in issues],
        "records": [asdict(record) for record in consolidate_records(records)],
        "stock_matches": [asdict(match) for match in matches],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prévisualise ou applique des débits atelier Progers/Orgadata.")
    parser.add_argument("files", nargs="+", type=Path, help="Fichiers .txt/.pdf à analyser.")
    parser.add_argument("--apply", action="store_true", help="Applique les sorties de stock. Sans cette option: prévisualisation.")
    parser.add_argument("--source-location", default="WH/Stock", help="Emplacement stock source.")
    parser.add_argument("--dest-location", default="Production Ateliers", help="Emplacement destination atelier.")
    parser.add_argument("--allow-missing", action="store_true", help="Autorise --apply malgré des références inconnues.")
    parser.add_argument("--allow-shortage", action="store_true", help="Autorise --apply malgré du stock insuffisant.")
    parser.add_argument("--json-out", type=Path, help="Écrit la prévisualisation complète en JSON.")
    args = parser.parse_args()

    records: list[DebitRecord] = []
    issues: list[DebitIssue] = []
    for path in args.files:
        if not path.exists():
            issues.append(DebitIssue("error", "missing_file", str(path), None, None, "Fichier introuvable."))
            continue
        parsed_records, parsed_issues = parse_file(path)
        records.extend(parsed_records)
        issues.extend(parsed_issues)

    summary = build_summary(records, issues)
    matches = preview_stock(records, args.source_location) if records else []
    match_counts = Counter(match.status for match in matches)
    summary["stock_match_status"] = dict(sorted(match_counts.items()))

    print("# Prévisualisation débit atelier")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    for issue in issues[:20]:
        location = f"ligne {issue.row}" if issue.row else "global"
        print(f"{issue.severity.upper()}: {issue.code} ({issue.source}, {location}, {issue.reference or '-'}) - {issue.message}")
    if len(issues) > 20:
        print(f"INFO: {len(issues) - 20} autres alertes non affichées. Utiliser --json-out pour le détail.")

    for match in [match for match in matches if match.status != "ok"][:20]:
        print(
            f"{match.status.upper()}: {match.supplier}/{match.reference} demandé={match.requested_quantity:g} "
            f"dispo={match.available_quantity:g} manque={match.missing_quantity:g}"
        )

    if args.json_out:
        write_json(args.json_out, records, issues, summary, matches)
        print(f"JSON: {args.json_out}")

    blocking_errors = [issue for issue in issues if issue.severity == "error"]
    missing = [match for match in matches if match.status == "not_found"]
    shortages = [match for match in matches if match.status == "shortage"]

    if args.apply and blocking_errors:
        print("FAIL: erreurs bloquantes de parsing. Corriger les fichiers avant import.", file=sys.stderr)
        return 1
    if args.apply and missing and not args.allow_missing:
        print("FAIL: références inconnues. Corriger le stock ou relancer avec --allow-missing.", file=sys.stderr)
        return 1
    if args.apply and shortages and not args.allow_shortage:
        print("FAIL: stock insuffisant. Corriger le stock ou relancer avec --allow-shortage.", file=sys.stderr)
        return 1

    if args.apply:
        stats = apply_debits(records, args.source_location, args.dest_location, args.allow_shortage)
        print("# Débit appliqué")
    else:
        stats = {"created_moves": 0, "updated_source_quants": 0, "updated_dest_quants": 0, "skipped_missing": 0}
        print("# Dry-run: aucune écriture en base")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

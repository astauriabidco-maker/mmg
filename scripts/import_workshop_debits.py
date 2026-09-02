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
    cut_left_deg: float | None = None
    cut_right_deg: float | None = None
    cut_orientation: str | None = None


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
        r"Affaire\s+N[°º]\s*(MMG[\w./-]+)",
        r"Affaire\s*:\s*([A-Z0-9_-]+)",
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


PROGES_FABRICATION_HEADER_RE = re.compile(
    r"R\S*F\S*RENCE\s+D\S*SIGNATION\s+COLORIS\s+QT\S*\s+D\S*BIT\s+COUPE",
    re.IGNORECASE,
)
PROGES_FABRICATION_PROFILE_RE = re.compile(
    r"^\s*(?P<reference>\S+)\s+"
    r"(?P<designation>.+?)\s+"
    r"(?P<color>\S+)\s+"
    r"(?P<quantity>\d+(?:[,.]\d+)?)\s+"
    r"(?P<length>\d+(?:[,.]\d+)?)\s+"
    r"(?P<cut_left>\d+(?:[,.]\d+)?)\s*/\s*"
    r"(?P<cut_right>\d+(?:[,.]\d+)?)"
    r"(?:\s+(?P<orientation>.*?))?\s*$",
    re.IGNORECASE,
)
PROGES_FABRICATION_ACCESSORY_RE = re.compile(
    r"^\s*(?P<reference>\S+)\s+"
    r"(?P<designation>.+?)\s+"
    r"(?P<color>\S+)\s+"
    r"(?P<quantity>\d+(?:[,.]\d+)?)\s+"
    r"(?P<unit>paire|pi\S*ce|unit\S*|pce|ml|m\S*tre|m)\s*$",
    re.IGNORECASE,
)
PROGES_FABRICATION_POSITION_RE = re.compile(
    r"\bREPERE\s*:\s*([A-Z0-9._/-]+)",
    re.IGNORECASE,
)
PROGES_FABRICATION_SECTIONS = {
    "K6": "KOMMERLING",
    "QU": "QUINCAILLERIE",
    "RX": "ROTO",
    "SG": "VITRAGE",
    "X1": "PROGES",
}
PROGES_CALCULATION_REFERENCES = {
    "HFFO",
    "LFFO",
    "LFFOP",
    "LFFOS",
    "LCREMONE",
}


def is_proges_fabrication_text(text: str) -> bool:
    upper = text.upper()
    return (
        "LOGICIEL PROGES" in upper
        and "FICHE DE FABRICATION" in upper
        and bool(PROGES_FABRICATION_HEADER_RE.search(text))
    )


def _proges_section_supplier(section: str | None) -> str:
    if section:
        return PROGES_FABRICATION_SECTIONS.get(section.upper(), "PROGES")
    return "PROGES"


def _normalize_proges_unit(value: str) -> str:
    normalized = value.lower()
    if (
        normalized == "pce"
        or (normalized.startswith("pi") and normalized.endswith("ce"))
        or normalized.startswith("unit")
    ):
        return "pce"
    if normalized == "m" or (
        normalized.startswith("m") and normalized.endswith("tre")
    ):
        return "ml"
    return normalized


def parse_proges_fabrication_pdf(
    path: Path,
    text: str,
) -> tuple[list[DebitRecord], list[DebitIssue]]:
    """Parse PROGES fabrication sheets containing material cutting tables."""

    project_reference = detect_project_reference(text)
    records: list[DebitRecord] = []
    issues: list[DebitIssue] = []
    current_position: str | None = None
    current_section: str | None = None

    for row_number, raw_line in enumerate(text.splitlines(), start=1):
        line = clean_text(raw_line)
        if not line:
            continue

        position_match = PROGES_FABRICATION_POSITION_RE.search(line)
        if position_match:
            current_position = position_match.group(1)
            continue

        if line.upper() in PROGES_FABRICATION_SECTIONS:
            current_section = line.upper()
            continue

        # pdfplumber preserves the fixed-width PROGES columns. Reading them
        # before the whitespace-normalized fallback also supports references
        # containing spaces, such as "GV 15 M3".
        if raw_line.startswith(" ") and len(raw_line) >= 59:
            layout_reference = clean_text(raw_line[1:14])
            layout_designation = clean_text(raw_line[14:41])
            layout_color = clean_text(raw_line[41:53])
            layout_quantity = parse_number(raw_line[53:58])
            layout_tail = clean_text(raw_line[58:])
            if (
                layout_reference
                and layout_designation
                and layout_color
                and layout_quantity is not None
                and layout_reference.upper() not in PROGES_CALCULATION_REFERENCES
            ):
                layout_profile = re.match(
                    r"^(?P<length>\d+(?:[,.]\d+)?)\s+"
                    r"(?P<cut_left>\d+(?:[,.]\d+)?)\s*/\s*"
                    r"(?P<cut_right>\d+(?:[,.]\d+)?)"
                    r"(?:\s+(?P<orientation>.*?))?$",
                    layout_tail,
                )
                if layout_profile:
                    records.append(
                        DebitRecord(
                            source=path.name,
                            row=row_number,
                            supplier=_proges_section_supplier(current_section),
                            reference=layout_reference,
                            designation=layout_designation,
                            quantity=layout_quantity,
                            unit="pce",
                            project_reference=project_reference,
                            color=layout_color,
                            length_mm=parse_number(layout_profile.group("length")),
                            position=current_position,
                            cut_left_deg=parse_number(layout_profile.group("cut_left")),
                            cut_right_deg=parse_number(layout_profile.group("cut_right")),
                            cut_orientation=clean_text(
                                layout_profile.group("orientation")
                            )
                            or None,
                        )
                    )
                    continue
                if re.fullmatch(r"\S+", layout_tail):
                    records.append(
                        DebitRecord(
                            source=path.name,
                            row=row_number,
                            supplier=_proges_section_supplier(current_section),
                            reference=layout_reference,
                            designation=layout_designation,
                            quantity=layout_quantity,
                            unit=_normalize_proges_unit(layout_tail),
                            project_reference=project_reference,
                            color=layout_color,
                            position=current_position,
                        )
                    )
                    continue

        profile_match = PROGES_FABRICATION_PROFILE_RE.match(line)
        if profile_match:
            reference = profile_match.group("reference").strip()
            if reference.upper() in PROGES_CALCULATION_REFERENCES:
                continue
            quantity = parse_number(profile_match.group("quantity"))
            length_mm = parse_number(profile_match.group("length"))
            cut_left = parse_number(profile_match.group("cut_left"))
            cut_right = parse_number(profile_match.group("cut_right"))
            if quantity is None or length_mm is None:
                continue
            records.append(
                DebitRecord(
                    source=path.name,
                    row=row_number,
                    supplier=_proges_section_supplier(current_section),
                    reference=reference,
                    designation=clean_text(profile_match.group("designation")),
                    quantity=quantity,
                    unit="pce",
                    project_reference=project_reference,
                    color=clean_text(profile_match.group("color")) or None,
                    length_mm=length_mm,
                    position=current_position,
                    cut_left_deg=cut_left,
                    cut_right_deg=cut_right,
                    cut_orientation=clean_text(profile_match.group("orientation")) or None,
                )
            )
            continue

        accessory_match = PROGES_FABRICATION_ACCESSORY_RE.match(line)
        if accessory_match:
            reference = accessory_match.group("reference").strip()
            if reference.upper() in PROGES_CALCULATION_REFERENCES:
                continue
            quantity = parse_number(accessory_match.group("quantity"))
            if quantity is None:
                continue
            records.append(
                DebitRecord(
                    source=path.name,
                    row=row_number,
                    supplier=_proges_section_supplier(current_section),
                    reference=reference,
                    designation=clean_text(accessory_match.group("designation")),
                    quantity=quantity,
                    unit=_normalize_proges_unit(accessory_match.group("unit")),
                    project_reference=project_reference,
                    color=clean_text(accessory_match.group("color")) or None,
                    position=current_position,
                )
            )

    if not records:
        issues.append(
            DebitIssue(
                "error",
                "no_proges_fabrication_records",
                path.name,
                None,
                None,
                "Aucune ligne de fabrication ou de débit PROGES exploitable.",
            )
        )
    return records, issues


ORGADATA_SECTION_RE = re.compile(
    r"^\s*(Cortizo|Technal|Hydro|Sepalumic)\s+([A-Za-z0-9./_-]+)\s+(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
ORGADATA_BAR_RE = re.compile(r"^\s*([0-9]+)\s+Pce\s+[àaá]\s+([0-9 ]+(?:[,.][0-9]+)?)\s*mm", re.IGNORECASE)
CORTIZO_DIRECT_ITEM_RE = re.compile(
    r"^\s*(?P<ordered>\d[\d ]*)\s+pce\s*\((?P<required>\d[\d ]*)\)\s+"
    r"(?P<reference>[A-Z0-9][A-Z0-9._/-]*)\s+(?P<designation>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
CORTIZO_PACK_ITEM_RE = re.compile(
    r"^\s*(?P<packs>\d+)\s+UV\s+[aàá]\s+"
    r"(?P<pack_size>\d{1,3}(?:[ .]\d{3})*|\d+)(?:\s+pce)?\s+"
    r"(?P<reference>[A-Z0-9][A-Z0-9._/-]*)\s+(?P<designation>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
CORTIZO_REQUIRED_RE = re.compile(
    r"^\s*(?:pce\s*)?\((?P<required>\d[\d ]*)\)\s*(?P<continuation>.*)$",
    re.IGNORECASE,
)
CORTIZO_PRICE_SUFFIX_RE = re.compile(
    r"\s+\d[\d ]*,\d{2}\s+\d[\d ]*,\d{2}\s*$"
)
CORTIZO_COLORS = ("7016CM", "BLANC", "NOIR", "GRIS")


ORGADATA_FABRICATION_HEADER_RE = re.compile(
    r"\bPosition\s+Syst\S*me\s+Type\s+Dimensions\s+Finition\s+Quantit\S*",
    re.IGNORECASE,
)
ORGADATA_FABRICATION_LINE_RE = re.compile(
    r"^\s*(?P<position>[A-Z]{1,5}\d+[A-Z0-9._/-]*)\s+"
    r"(?P<system>.+?)\s+"
    r"(?P<opening_type>Fixe|Porte[- ]fen[eê]tre|Fen[eê]tre|Porte|Coulissant|"
    r"Levant[- ]coulissant|Battant|Oscillo[- ]battant|Soufflet|Pivotant|"
    r"Pliant(?:\s*/\s*accord[ée]on)?|Verri[eè]re|Fa[cç]ade)\s+"
    r"(?P<width>\d+(?:[,.]\d+)?)\s*[x×]\s*"
    r"(?P<height>\d+(?:[,.]\d+)?)\s*mm\s+"
    r"(?P<finish>.+?)\s+"
    r"(?P<quantity>\d+(?:[,.]\d+)?)\s*$",
    re.IGNORECASE,
)
ORGADATA_FABRICATION_DETAIL_RE = re.compile(
    r"^\s*(?P<label>Vitrage|Glass|Couleur|Coloris|Finition|Accessoires?|"
    r"Quincaillerie|Remarques?|Notes?)\s*:\s*(?P<value>.+?)\s*$",
    re.IGNORECASE,
)


def is_orgadata_fabrication_text(text: str) -> bool:
    upper = text.upper()
    return (
        ("ORGADATA" in upper or "LOGIKAL" in upper)
        and "BON D'ATELIER" in upper
        and bool(ORGADATA_FABRICATION_HEADER_RE.search(text))
    )


def _orgadata_fabrication_material(system: str, text: str) -> str | None:
    haystack = f"{system} {text}".upper()
    if any(token in haystack for token in ("ALU", "ALUMINIUM", "CORTIZO", "TECHNAL", "HYDRO", "SEPALUMIC")):
        return "ALU"
    if "PVC" in haystack or "KOMMERLING" in haystack or "KÖMMERLING" in haystack:
        return "PVC"
    return None


def _apply_orgadata_detail(record: dict[str, Any], label: str, value: str) -> None:
    key = clean_text(label).lower()
    value = clean_text(value)
    if not value:
        return
    if key in {"vitrage", "glass"}:
        record["glazing"] = value
    elif key in {"couleur", "coloris", "finition"}:
        record["finish"] = value
    elif key in {"accessoire", "accessoires", "quincaillerie"}:
        record["accessories"] = [
            clean_text(part) for part in re.split(r"[,;]", value) if clean_text(part)
        ]
    elif key in {"remarque", "remarques", "note", "notes"}:
        record["remarks"] = value


def parse_orgadata_fabrication_pdf(
    path: Path,
    text: str,
) -> tuple[list[dict[str, Any]], list[DebitIssue]]:
    """Parse ORGADATA/LogiKal workshop fabrication sheets.

    These records describe manufactured openings and workshop instructions.
    They are intentionally not DebitRecord instances because stock
    reservations must continue to come from the dedicated CUTTING document.
    """

    project_reference = detect_project_reference(text)
    records: list[dict[str, Any]] = []
    issues: list[DebitIssue] = []
    current: dict[str, Any] | None = None

    for row_number, raw_line in enumerate(text.splitlines(), start=1):
        line = clean_text(raw_line)
        if not line:
            continue

        match = ORGADATA_FABRICATION_LINE_RE.match(line)
        if match:
            width = parse_number(match.group("width"))
            height = parse_number(match.group("height"))
            quantity = parse_number(match.group("quantity"))
            if width is None or height is None or quantity is None:
                issues.append(
                    DebitIssue(
                        "warning",
                        "invalid_orgadata_fabrication_line",
                        path.name,
                        row_number,
                        match.group("position"),
                        f"Ligne fabrication ORGADATA ignorée: {line}",
                    )
                )
                current = None
                continue
            current = {
                "source": path.name,
                "row": row_number,
                "project_reference": project_reference,
                "position": clean_text(match.group("position")),
                "system": clean_text(match.group("system")),
                "opening_type": clean_text(match.group("opening_type")),
                "width_mm": width,
                "height_mm": height,
                "finish": clean_text(match.group("finish")),
                "quantity": quantity,
                "material": _orgadata_fabrication_material(match.group("system"), text),
                "glazing": None,
                "accessories": [],
                "remarks": None,
            }
            records.append(current)
            continue

        detail_match = ORGADATA_FABRICATION_DETAIL_RE.match(line)
        if detail_match and current is not None:
            _apply_orgadata_detail(
                current,
                detail_match.group("label"),
                detail_match.group("value"),
            )

    if is_orgadata_fabrication_text(text) and not records:
        issues.append(
            DebitIssue(
                "error",
                "no_orgadata_fabrication_records",
                path.name,
                None,
                None,
                "Aucune ligne d'ouvrage ORGADATA exploitable dans le bon d'atelier.",
            )
        )
    return records, issues


def is_cortizo_order_text(text: str) -> bool:
    upper = text.upper()
    has_columns = "CROQUIS QUANTITÉ / NUMÉRO" in upper
    has_order_rows = bool(
        CORTIZO_DIRECT_ITEM_RE.search(text)
        or CORTIZO_PACK_ITEM_RE.search(text)
    )
    return (
        "COMMANDE" in upper
        and bool(re.search(r"AFFAIRE\s+N[°º]\s*MMG", text, flags=re.IGNORECASE))
        and has_columns
        and has_order_rows
        and ("CORTIZO" in upper or bool(CORTIZO_PACK_ITEM_RE.search(text)))
    )


def _cortizo_designation_and_color(value: str) -> tuple[str, str | None]:
    designation = CORTIZO_PRICE_SUFFIX_RE.sub("", clean_text(value)).strip()
    upper = designation.upper()
    for color in CORTIZO_COLORS:
        if upper.endswith(f" {color}"):
            return designation[: -len(color)].strip(), color
    return designation, None


def _parse_cortizo_integer(value: str) -> float:
    return float(value.replace(" ", "").replace(".", ""))


def parse_cortizo_order_pdf(
    path: Path,
    text: str,
) -> tuple[list[DebitRecord], list[DebitIssue]]:
    """Parse an MMG/Cortizo purchase BOM using the parenthesized workshop need.

    ``2 UV à 25 pce (40)`` means two purchase packs of 25 pieces, while 40
    pieces are required by the workshop. Stock reservation must therefore use
    the parenthesized quantity and not the purchased pack quantity.
    """

    project_reference = detect_project_reference(text)
    records: list[DebitRecord] = []
    issues: list[DebitIssue] = []
    current: dict[str, Any] | None = None
    current_section: str | None = None

    def finish_current() -> None:
        nonlocal current
        if current is None:
            return
        if current["required"] is None:
            issues.append(
                DebitIssue(
                    "warning",
                    "missing_required_quantity",
                    path.name,
                    current["row"],
                    current["reference"],
                    (
                        "Quantité nécessaire absente; la quantité d'achat UV "
                        "n'est pas utilisée comme débit atelier."
                    ),
                )
            )
            current = None
            return
        designation, color = _cortizo_designation_and_color(
            " ".join(current["designation_parts"])
        )
        records.append(
            DebitRecord(
                source=path.name,
                row=current["row"],
                supplier="CORTIZO",
                reference=current["reference"],
                designation=designation or current["reference"],
                quantity=current["required"],
                unit="pce",
                project_reference=project_reference,
                color=color,
                position=current_section,
            )
        )
        current = None

    ignored_prefixes = (
        "--- PAGE",
        "AFFAIRE N°",
        "DATE:",
        "COMMANDE",
        "NOM AFFAIRE:",
        "TECHNICIEN:",
        "POSITIONS INCLUSES:",
        "CROQUIS QUANTITÉ /",
        "UNITÉ",
        "(NÉCESSAIRE)",
        "SOMME:",
        "TOTAL:",
        "PAGE ",
    )

    for row_number, raw_line in enumerate(text.splitlines(), start=1):
        line = clean_text(raw_line)
        direct_match = CORTIZO_DIRECT_ITEM_RE.match(line)
        pack_match = CORTIZO_PACK_ITEM_RE.match(line)
        if direct_match or pack_match:
            finish_current()
            match = direct_match or pack_match
            assert match is not None
            current = {
                "row": row_number,
                "reference": match.group("reference"),
                "required": (
                    _parse_cortizo_integer(match.group("required"))
                    if direct_match
                    else None
                ),
                "designation_parts": [match.group("designation")],
            }
            continue

        if line.upper() in {"FERRURE", "ACCESSOIRES"}:
            finish_current()
            current_section = line.capitalize()
            continue

        if current is None:
            continue
        if not line:
            finish_current()
            continue

        required_match = CORTIZO_REQUIRED_RE.match(line)
        if required_match and current["required"] is None:
            current["required"] = _parse_cortizo_integer(
                required_match.group("required")
            )
            continuation = clean_text(required_match.group("continuation"))
            if continuation:
                current["designation_parts"].append(continuation)
            continue

        if line.upper().startswith(ignored_prefixes):
            finish_current()
            continue
        current["designation_parts"].append(line)

    finish_current()
    if not records:
        issues.append(
            DebitIssue(
                "error",
                "no_cortizo_requirements",
                path.name,
                None,
                None,
                "Aucune ligne Cortizo avec quantité nécessaire exploitable.",
            )
        )
    return records, issues


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
        if is_proges_fabrication_text(text):
            return parse_proges_fabrication_pdf(path, text)
        if "Débit optimisé" in text:
            return parse_orgadata_optimized_pdf(path, text)
        if is_cortizo_order_text(text):
            return parse_cortizo_order_pdf(path, text)
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
    consolidated: dict[tuple, DebitRecord] = {}
    for record in records:
        key = (
            record.source,
            record.supplier,
            record.reference,
            record.unit,
            record.length_mm,
            record.cut_left_deg,
            record.cut_right_deg,
            record.cut_orientation,
        )
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
            cut_left_deg=existing.cut_left_deg,
            cut_right_deg=existing.cut_right_deg,
            cut_orientation=existing.cut_orientation,
        )
    return list(consolidated.values())


def build_summary(records: list[DebitRecord], issues: list[DebitIssue]) -> dict[str, Any]:
    consolidated = consolidate_records(records)
    return {
        "raw_records": len(records),
        "debit_lines": len(consolidated),
        "unique_references": len(
            {(record.supplier, record.reference) for record in consolidated}
        ),
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

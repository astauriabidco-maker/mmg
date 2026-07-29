from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Iterable


_MONEY = r"(?:\d{1,3}(?:[ \u00a0.]\d{3})*|\d+),\d{2}"
_PROGES_LINE = re.compile(
    rf"^(?P<quantity>\d+(?:[.,]\d+)?)\s+"
    rf"(?P<description>.+?)\s+"
    rf"(?P<width>\d+(?:[.,]\d+)?)\s+"
    rf"(?P<height>\d+(?:[.,]\d+)?)\s+"
    rf"(?P<unit_price>{_MONEY})\s+"
    rf"(?P<total_price>{_MONEY})$",
    re.IGNORECASE,
)
_ORGADATA_LINE = re.compile(
    rf"^(?P<position>.+?)\s+"
    rf"(?P<quantity>\d+(?:[.,]\d+)?)\s+Pce\s+"
    rf"(?P<unit_price>{_MONEY})\s+"
    rf"(?P<total_price>{_MONEY})$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CommercialQuoteAnalysis:
    source_system: str | None
    project_reference: str | None
    summary: dict[str, Any]
    records: list[dict[str, Any]]
    issues: list[dict[str, Any]]


def _clean(value: str) -> str:
    text = (value or "").replace("\u00a0", " ")
    for broken, repaired in {
        "FenŒtre": "Fenêtre",
        "fenŒtre": "fenêtre",
        "cotØs": "côtés",
        "CrØmone": "Crémone",
        "crØmone": "crémone",
        "tŒtiŁre": "têtière",
    }.items():
        text = text.replace(broken, repaired)
    return " ".join(text.split()).strip()


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    normalized = (
        _clean(value)
        .replace("EUR", "")
        .replace("€", "")
        .replace("%", "")
        .replace(" ", "")
        .replace(".", "")
        .replace(",", ".")
    )
    if not normalized:
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _as_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _number(value: str) -> float:
    return float(value.replace(",", "."))


def _page_lines(text: str) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    page_number = 1
    for raw_line in text.splitlines():
        marker = re.fullmatch(r"\s*--- PAGE (\d+) ---\s*", raw_line)
        if marker:
            page_number = int(marker.group(1))
            continue
        line = _clean(raw_line)
        if line:
            result.append((page_number, line))
    return result


def detect_commercial_quote_source(text: str, filename: str = "") -> str | None:
    haystack = _clean(f"{filename} {text[:30000]}").upper()
    if (
        "QTÉ DÉSIGNATION L H P.U. HT P.T. HT" in haystack
        or "EDITION DU CROQUIS DES CHÂSSIS" in haystack
        or "EDITION DU CROQUIS DES CHASSIS" in haystack
    ):
        return "PROGES"
    if (
        "POSITION QUANTITÉ DESCRIPTION PRIX TOTAL" in haystack
        or "POSITION QUANTITE DESCRIPTION PRIX TOTAL" in haystack
    ):
        return "ORGADATA"
    return None


def detect_commercial_quote_reference(text: str) -> str | None:
    patterns = (
        r"\bDevis\s+N[°º]\s*([^\r\n]+?)(?=\s+-\s+|\r?$)",
        r"\bDEVIS\s+N[°º]?\s*([^\r\n]+?)(?=\s+-\s+|\r?$)",
        r"\bRéférence\s*:\s*([^\r\n]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return _clean(match.group(1)).rstrip("-")
    return None


def _is_totals_or_footer(line: str) -> bool:
    upper = line.upper()
    return (
        upper.startswith("MONTANT TOTAL")
        or upper.startswith("TOTAL HT")
        or upper.startswith("REMISE")
        or upper.startswith("T.V.A")
        or upper.startswith("PRIX TOTAL")
        or upper.startswith("RÉSERVE DE PROPRIÉTÉ")
        or upper.startswith("RESERVE DE PROPRIETE")
        or upper.startswith("CONDITIONS GENERALES")
        or upper.startswith("CONDITIONS GÉNÉRALES")
        or upper.startswith("PAGE ")
    )


def _looks_like_position(line: str) -> bool:
    if len(line) > 60 or _is_totals_or_footer(line):
        return False
    upper = line.upper()
    excluded = (
        "MMG ",
        "DEVIS ",
        "QTÉ ",
        "QTE ",
        "DÉSIGNATION",
        "DESIGNATION",
        "DESCRIPTIF",
        "PANTIN",
        "RÉFÉRENCE",
        "REFERENCE",
    )
    if upper.startswith(excluded):
        return False
    return bool(
        re.match(
            r"^(?:F|PF|CH|WC|SDB|DGT|RDC|R\+|SALON|CUISINE|ENTRÉE|ENTREE|BUREAU)"
            r"[A-Z0-9 /+()._-]*$",
            upper,
        )
    )


def _details_until_next_record(
    lines: list[tuple[int, str]],
    start: int,
    matcher: re.Pattern[str],
    *,
    stop_on_position: bool = False,
) -> list[str]:
    details: list[str] = []
    for _, line in lines[start:]:
        if matcher.match(line) or _is_totals_or_footer(line):
            break
        if stop_on_position and _looks_like_position(line):
            break
        if line.upper().startswith(("QTÉ DÉSIGNATION", "POSITION QUANTITÉ", "POSITION QUANTITE")):
            continue
        if line.upper().startswith(("MMG - DEVIS", "DEVIS N°")):
            continue
        details.append(line)
    return details


def _parse_proges(lines: list[tuple[int, str]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    previous_line = ""
    current_position: str | None = None
    for index, (page, line) in enumerate(lines):
        if _looks_like_position(line):
            current_position = line
        elif line == previous_line and len(line) <= 60 and not _is_totals_or_footer(line):
            current_position = line

        match = _PROGES_LINE.match(line)
        previous_line = line
        if not match:
            continue

        details = _details_until_next_record(
            lines,
            index + 1,
            _PROGES_LINE,
            stop_on_position=True,
        )
        description = _clean(match.group("description"))
        record_number = len(records) + 1
        position = current_position or f"LIGNE-{record_number:03d}"
        records.append(
            {
                "line_number": record_number,
                "position": position,
                "description": description,
                "details": details,
                "quantity": _number(match.group("quantity")),
                "unit": "PCE",
                "width_mm": _number(match.group("width")),
                "height_mm": _number(match.group("height")),
                "unit_price": _as_float(_decimal(match.group("unit_price"))),
                "total_price": _as_float(_decimal(match.group("total_price"))),
                "source_page": page,
                "source_system": "PROGES",
            }
        )
        current_position = None
    return records


def _orgadata_dimensions(lines: Iterable[str]) -> tuple[float | None, float | None]:
    for line in lines:
        match = re.search(
            r"(\d+(?:[.,]\d+)?)\s*mm\s*x\s*(\d+(?:[.,]\d+)?)\s*mm",
            line,
            flags=re.IGNORECASE,
        )
        if match:
            return _number(match.group(1)), _number(match.group(2))
    return None, None


def _parse_orgadata(lines: list[tuple[int, str]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, (page, line) in enumerate(lines):
        match = _ORGADATA_LINE.match(line)
        if not match:
            continue
        details = _details_until_next_record(lines, index + 1, _ORGADATA_LINE)
        commercial_description = next(
            (
                value
                for value in details
                if value.lower() != "vue intérieure"
                and not value.lower().startswith("vue intérieure")
            ),
            match.group("position"),
        )
        width_mm, height_mm = _orgadata_dimensions(details)
        records.append(
            {
                "line_number": len(records) + 1,
                "position": _clean(match.group("position")),
                "description": commercial_description,
                "details": details,
                "quantity": _number(match.group("quantity")),
                "unit": "PCE",
                "width_mm": width_mm,
                "height_mm": height_mm,
                "unit_price": _as_float(_decimal(match.group("unit_price"))),
                "total_price": _as_float(_decimal(match.group("total_price"))),
                "source_page": page,
                "source_system": "ORGADATA",
            }
        )
    return records


def _extract_totals(lines: list[tuple[int, str]]) -> dict[str, Any]:
    gross_values: list[Decimal] = []
    discount_values: list[Decimal] = []
    discount_percentages: list[Decimal] = []
    net_subtotal: Decimal | None = None
    tax_rate: Decimal | None = None
    tax_amount: Decimal | None = None
    grand_total: Decimal | None = None

    for _, line in lines:
        upper = line.upper()
        label_upper = re.sub(r"(?<=[A-Z]),(?=[A-Z])", ".", upper)
        money_values = [_decimal(value) for value in re.findall(_MONEY, line)]
        money_values = [value for value in money_values if value is not None]
        if label_upper.startswith("TOTAL HT NET") and money_values:
            net_subtotal = money_values[-1]
        elif label_upper.startswith("TOTAL HT") and money_values:
            gross_values.append(money_values[-1])
        elif label_upper.startswith("MONTANT TOTAL H.T") and money_values:
            gross_values.append(money_values[-1])
        elif label_upper.startswith("REMISE"):
            if money_values:
                discount_values.append(abs(money_values[-1]))
            percentages = re.findall(r"([+-]?\s*\d+(?:[.,]\d+)?)\s*%", line)
            discount_percentages.extend(
                abs(value)
                for raw in percentages
                if (value := _decimal(raw)) is not None
            )
        elif label_upper.startswith("T.V.A") and money_values:
            tax_amount = money_values[-1] if len(money_values) > 1 else None
            percentage = re.search(r"(\d+(?:[.,]\d+)?)\s*%", line)
            if percentage:
                tax_rate = _decimal(percentage.group(1))
        elif label_upper.startswith(("PRIX TOTAL", "MONTANT TOTAL T.T.C")) and money_values:
            grand_total = money_values[-1]

    gross_subtotal = gross_values[0] if gross_values else None
    if net_subtotal is None and len(gross_values) > 1:
        net_subtotal = gross_values[-1]
    if gross_subtotal is not None and net_subtotal is None:
        explicit_discount = sum(discount_values, Decimal("0"))
        if explicit_discount:
            net_subtotal = gross_subtotal - explicit_discount
        else:
            running = gross_subtotal
            for percentage in discount_percentages:
                running *= Decimal("1") - percentage / Decimal("100")
            net_subtotal = running
    if net_subtotal is None:
        net_subtotal = gross_subtotal

    discount_amount = (
        gross_subtotal - net_subtotal
        if gross_subtotal is not None and net_subtotal is not None
        else sum(discount_values, Decimal("0"))
    )
    effective_discount_pct = (
        (discount_amount / gross_subtotal * Decimal("100"))
        if gross_subtotal and discount_amount is not None
        else Decimal("0")
    )
    return {
        "subtotal_before_discount": _as_float(gross_subtotal),
        "discount_amount": _as_float(discount_amount),
        "discount_percentages": [_as_float(value) for value in discount_percentages],
        "effective_discount_pct": _as_float(effective_discount_pct),
        "subtotal_after_discount": _as_float(net_subtotal),
        "tax_rate": _as_float(tax_rate),
        "tax_amount": _as_float(tax_amount),
        "grand_total": _as_float(grand_total),
    }


def _issue(code: str, message: str, severity: str = "error") -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "source": "commercial_quote",
        "row": None,
        "reference": None,
        "message": message,
    }


def analyze_commercial_quote(
    text: str,
    filename: str = "",
    declared_source: str | None = None,
) -> CommercialQuoteAnalysis:
    lines = _page_lines(text)
    detected_source = detect_commercial_quote_source(text, filename)
    source = detected_source or (declared_source or "").upper() or None
    records = (
        _parse_proges(lines)
        if source == "PROGES"
        else _parse_orgadata(lines)
        if source == "ORGADATA"
        else []
    )
    totals = _extract_totals(lines)
    computed_lines_total = round(
        sum(float(record.get("total_price") or 0) for record in records),
        2,
    )
    total_quantity = sum(float(record.get("quantity") or 0) for record in records)
    expected_lines_total = totals.get("subtotal_before_discount")
    variance = (
        round(computed_lines_total - float(expected_lines_total), 2)
        if expected_lines_total is not None
        else None
    )
    issues: list[dict[str, Any]] = []
    if not source:
        issues.append(
            _issue(
                "commercial_quote_source_unknown",
                "Le format du chiffrage n'a pas été reconnu comme PROGES ou ORGADATA.",
            )
        )
    if declared_source and detected_source and declared_source.upper() != detected_source:
        issues.append(
            _issue(
                "commercial_quote_source_mismatch",
                (
                    f"Le fichier ressemble à {detected_source}, mais il a été déclaré "
                    f"{declared_source.upper()}."
                ),
                "warning",
            )
        )
    if not records:
        issues.append(
            _issue(
                "commercial_quote_lines_missing",
                "Aucune ligne commerciale chiffrée n'a été détectée.",
            )
        )
    if any(float(record.get("unit_price") or 0) <= 0 for record in records):
        issues.append(
            _issue(
                "commercial_quote_zero_price",
                "Une ou plusieurs lignes ont un prix unitaire nul.",
            )
        )
    if expected_lines_total is None:
        issues.append(
            _issue(
                "commercial_quote_totals_missing",
                "Le total HT du document n'a pas été détecté.",
                "warning",
            )
        )
    elif variance is not None and abs(variance) > 0.05:
        issues.append(
            _issue(
                "commercial_quote_total_mismatch",
                (
                    f"La somme des lignes ({computed_lines_total:.2f} EUR) diffère du "
                    f"total HT brut ({float(expected_lines_total):.2f} EUR)."
                ),
            )
        )
    summary = {
        "line_count": len(records),
        "total_quantity": total_quantity,
        "computed_lines_total": computed_lines_total,
        "lines_total_variance": variance,
        **totals,
    }
    return CommercialQuoteAnalysis(
        source_system=source,
        project_reference=detect_commercial_quote_reference(text),
        summary=summary,
        records=records,
        issues=issues,
    )


def compare_commercial_quote_versions(
    previous: list[dict[str, Any]],
    current: list[dict[str, Any]],
) -> dict[str, Any]:
    def key(record: dict[str, Any]) -> str:
        return _clean(
            str(record.get("position") or record.get("description") or record.get("line_number"))
        ).upper()

    previous_by_key = {key(record): record for record in previous}
    current_by_key = {key(record): record for record in current}
    added = sorted(set(current_by_key) - set(previous_by_key))
    removed = sorted(set(previous_by_key) - set(current_by_key))
    changed: list[dict[str, Any]] = []
    for record_key in sorted(set(previous_by_key) & set(current_by_key)):
        before = previous_by_key[record_key]
        after = current_by_key[record_key]
        fields = [
            field
            for field in ("quantity", "width_mm", "height_mm", "unit_price", "total_price")
            if before.get(field) != after.get(field)
        ]
        if fields:
            changed.append(
                {
                    "key": record_key,
                    "fields": fields,
                    "before": {field: before.get(field) for field in fields},
                    "after": {field: after.get(field) for field in fields},
                }
            )
    previous_total = round(
        sum(float(record.get("total_price") or 0) for record in previous),
        2,
    )
    current_total = round(
        sum(float(record.get("total_price") or 0) for record in current),
        2,
    )
    return {
        "has_changes": bool(added or removed or changed),
        "added_count": len(added),
        "removed_count": len(removed),
        "changed_count": len(changed),
        "added": added,
        "removed": removed,
        "changed": changed,
        "previous_total": previous_total,
        "current_total": current_total,
        "total_delta": round(current_total - previous_total, 2),
    }

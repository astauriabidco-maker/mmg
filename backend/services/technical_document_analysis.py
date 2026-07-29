from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Any

from backend.services.commercial_quote_analysis import analyze_commercial_quote
from scripts.import_workshop_debits import (
    build_summary,
    consolidate_records,
    extract_pdf_text,
    parse_file,
    read_text_file,
)


@dataclass(frozen=True)
class TechnicalDocumentAnalysis:
    status: str
    detected_document_type: str
    detected_source_system: str | None
    detected_project_reference: str | None
    summary: dict[str, Any]
    records: list[dict[str, Any]]
    issues: list[dict[str, Any]]


def _document_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return extract_pdf_text(path)
    if path.suffix.lower() in {".txt", ".csv", ".dat", ".cut"}:
        return read_text_file(path)
    return ""


def _detect_source(text: str, filename: str, declared_source: str) -> str | None:
    haystack = f"{filename}\n{text[:12000]}".upper()
    if "ORGADATA" in haystack or "LOGIKAL" in haystack or "DÉBIT OPTIMISÉ" in haystack:
        return "ORGADATA"
    if "SEPALUMIC GAMME" in haystack or "VALORISATION DE COMMANDE" in haystack:
        return "PROGES"
    if (
        "COMMANDE" in haystack
        and "CROQUIS QUANTITÉ / NUMÉRO" in haystack
        and re.search(r"AFFAIRE\s+N[°º]\s*MMG", haystack)
    ):
        # This is an MMG-derived Cortizo purchase BOM, not proof of the CAD
        # software that produced the underlying design.
        return "INTERNAL"
    return declared_source or None


def _detect_project_reference(text: str) -> str | None:
    patterns = (
        r"Affaire\s+N[°º]\s*(MMG[\w./-]+)",
        r"\bDevis\s+N[°º]\s*([A-Z0-9][A-Z0-9._/-]*)",
        r"\bDEVIS\s+N[°º]?\s*([A-Z0-9][A-Z0-9._/-]*)",
        r"Affaire\s*:\s*([A-Z0-9_-]+)",
        r"N[°º]\s*offre\s*:\s*([A-Z0-9_-]+)",
        r"Offre\s+n[°º]\s*:\s*([A-Z0-9_-]+)",
        r"Référence\s+Commande\s*:\s*([^\r\n]+)",
        r"R\S*f\S*rence\s+Commande\s*:\s*([^\r\n]+)",
        r"\b(DEV-\d{4}(?:-\d{2}){2}-\d+)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return " ".join(match.group(1).split()).strip()

    # SEPVER exports place the command reference immediately before the date.
    lines = [" ".join(line.split()).strip() for line in text.splitlines()]
    for index, line in enumerate(lines):
        if re.fullmatch(r"\d{2}[-/]\d{2}[-/]\d{4}", line) and index:
            for candidate in reversed(lines[:index]):
                if candidate and "GAMME" not in candidate.upper():
                    return candidate
    return None


def _detect_type(text: str, filename: str, declared_type: str) -> str:
    haystack = f"{filename}\n{text[:12000]}".upper()
    if "DÉBIT OPTIMISÉ" in haystack or filename.upper().startswith("SEP"):
        return "CUTTING"
    if (
        "COMMANDE" in haystack
        and "CROQUIS QUANTITÉ / NUMÉRO" in haystack
        and re.search(r"AFFAIRE\s+N[°º]\s*MMG", haystack)
    ):
        return "CUTTING"
    if "BON D'ATELIER" in haystack:
        return "FABRICATION"
    if "VALORISATION DE COMMANDE" in haystack:
        return "VALUATION"
    if "DEVIS N°" in haystack or "OFFRE NOUVEAU DOCUMENT" in haystack:
        return "QUOTING"
    return declared_type


def analyze_technical_document(
    path: Path,
    declared_type: str,
    declared_source: str,
    declared_reference: str | None = None,
) -> TechnicalDocumentAnalysis:
    try:
        text = _document_text(path)
    except Exception as exc:
        issue = {
            "severity": "error",
            "code": "unreadable_document",
            "source": path.name,
            "row": None,
            "reference": None,
            "message": f"Document illisible: {exc}",
        }
        return TechnicalDocumentAnalysis(
            status="FAILED",
            detected_document_type=declared_type,
            detected_source_system=declared_source or None,
            detected_project_reference=None,
            summary={
                "raw_records": 0,
                "debit_lines": 0,
                "total_quantity": 0,
                "suppliers": {},
                "units": {},
                "sources": {path.name: 1},
                "issues": {"unreadable_document": 1},
                "issue_count": 1,
            },
            records=[],
            issues=[issue],
        )
    detected_type = _detect_type(text, path.name, declared_type)
    detected_source = _detect_source(text, path.name, declared_source)
    detected_reference = _detect_project_reference(text)
    records = []
    issues = []

    if declared_type == "QUOTING":
        quote_analysis = analyze_commercial_quote(
            text,
            path.name,
            declared_source or None,
        )
        records = quote_analysis.records
        issues.extend(quote_analysis.issues)
        summary = quote_analysis.summary
        detected_source = quote_analysis.source_system or detected_source
        detected_reference = quote_analysis.project_reference or detected_reference
        if records and not any(issue.get("severity") == "error" for issue in issues):
            status = "PARSED_WITH_WARNINGS" if issues else "PARSED"
        else:
            status = "FAILED"
    elif declared_type == "CUTTING":
        try:
            parsed_records, parsed_issues = parse_file(path)
        except Exception as exc:
            parsed_records = []
            parsed_issues = []
            issues.append(
                {
                    "severity": "error",
                    "code": "parser_failure",
                    "source": path.name,
                    "row": None,
                    "reference": detected_reference,
                    "message": f"Analyse du débit impossible: {exc}",
                }
            )
        records = [asdict(record) for record in consolidate_records(parsed_records)]
        issues.extend(asdict(issue) for issue in parsed_issues)
        summary = build_summary(parsed_records, parsed_issues)
        if records:
            status = "PARSED_WITH_WARNINGS" if issues else "PARSED"
        else:
            status = "FAILED"
    else:
        summary = {
            "raw_records": 0,
            "debit_lines": 0,
            "total_quantity": 0,
            "suppliers": {},
            "units": {},
            "sources": {path.name: 1},
            "issues": {},
        }
        status = "DOCUMENT_ONLY"

    expected_reference = (declared_reference or "").strip() or None
    if expected_reference and detected_reference and expected_reference != detected_reference:
        issues.append(
            {
                "severity": "warning",
                "code": "project_reference_mismatch",
                "source": path.name,
                "row": None,
                "reference": detected_reference,
                "message": (
                    f"Référence détectée {detected_reference!r}, différente de "
                    f"la référence déclarée {expected_reference!r}."
                ),
            }
        )
        status = "PARSED_WITH_WARNINGS" if records else "FAILED"

    if detected_type != declared_type and declared_type in {"QUOTING", "FABRICATION", "CUTTING"}:
        issues.append(
            {
                "severity": "warning",
                "code": "document_type_mismatch",
                "source": path.name,
                "row": None,
                "reference": detected_reference,
                "message": (
                    f"Le contenu ressemble à {detected_type}, mais le fichier a été "
                    f"classé {declared_type}."
                ),
            }
        )
        status = "PARSED_WITH_WARNINGS" if records else "FAILED"

    summary = dict(summary)
    summary["detected_project_reference"] = detected_reference
    summary["detected_source_system"] = detected_source
    summary["detected_document_type"] = detected_type
    summary["issue_count"] = len(issues)
    return TechnicalDocumentAnalysis(
        status=status,
        detected_document_type=detected_type,
        detected_source_system=detected_source,
        detected_project_reference=detected_reference,
        summary=summary,
        records=records,
        issues=issues,
    )

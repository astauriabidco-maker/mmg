from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


PRODUCTION_DOCUMENT_TYPES = ("FABRICATION", "CUTTING")


def _record_key(record: dict[str, Any]) -> tuple:
    length = record.get("length_mm")
    cut_left = record.get("cut_left_deg")
    cut_right = record.get("cut_right_deg")
    return (
        str(record.get("supplier") or "").strip().upper(),
        str(record.get("reference") or "").strip().upper(),
        str(record.get("unit") or "").strip().lower(),
        round(float(length), 3) if length not in (None, "") else None,
        round(float(cut_left), 3) if cut_left not in (None, "") else None,
        round(float(cut_right), 3) if cut_right not in (None, "") else None,
        str(record.get("cut_orientation") or "").strip().upper() or None,
    )


def _aggregate_records(records: Iterable[dict[str, Any]]) -> dict[tuple, dict[str, Any]]:
    aggregated: dict[tuple, dict[str, Any]] = {}
    for record in records or []:
        key = _record_key(record)
        if not key[1]:
            continue
        quantity = float(record.get("quantity") or 0)
        if key not in aggregated:
            aggregated[key] = {
                "supplier": key[0],
                "reference": key[1],
                "unit": key[2],
                "length_mm": key[3],
                "cut_left_deg": key[4],
                "cut_right_deg": key[5],
                "cut_orientation": key[6],
                "designation": record.get("designation"),
                "quantity": 0.0,
            }
        aggregated[key]["quantity"] += quantity
    return aggregated


def compare_material_versions(
    previous_records: Iterable[dict[str, Any]],
    current_records: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    previous = _aggregate_records(previous_records)
    current = _aggregate_records(current_records)
    added = []
    removed = []
    changed = []

    for key in sorted(current.keys() - previous.keys()):
        added.append(current[key])
    for key in sorted(previous.keys() - current.keys()):
        removed.append(previous[key])
    for key in sorted(current.keys() & previous.keys()):
        before = previous[key]
        after = current[key]
        if abs(before["quantity"] - after["quantity"]) > 1e-9:
            changed.append(
                {
                    **after,
                    "previous_quantity": before["quantity"],
                    "quantity_delta": after["quantity"] - before["quantity"],
                }
            )

    quantity_delta = sum(item["quantity"] for item in current.values()) - sum(
        item["quantity"] for item in previous.values()
    )
    has_changes = bool(added or removed or changed)
    return {
        "has_changes": has_changes,
        "added_count": len(added),
        "removed_count": len(removed),
        "changed_count": len(changed),
        "quantity_delta": quantity_delta,
        "added": added,
        "removed": removed,
        "changed": changed,
    }


def build_document_matrix(versions: Iterable[Any]) -> dict[str, Any]:
    latest_by_type: dict[str, Any] = {}
    source_counts: dict[str, int] = defaultdict(int)
    for version in versions or []:
        latest_by_type[version.document_type] = version
        source_counts[version.source_system] += 1

    references: set[str] = set()
    for document_type in {*PRODUCTION_DOCUMENT_TYPES, "VALUATION"}:
        version = latest_by_type.get(document_type)
        if not version:
            continue
        reference = (
            version.detected_project_reference
            or version.source_reference
            or ""
        ).strip()
        if reference:
            references.add(reference)

    required = []
    for document_type in PRODUCTION_DOCUMENT_TYPES:
        version = latest_by_type.get(document_type)
        required.append(
            {
                "document_type": document_type,
                "required": True,
                "present": bool(version),
                "version_number": version.version_number if version else None,
                "analysis_status": version.analysis_status if version else None,
                "filename": version.original_filename if version else None,
            }
        )
    valuation = latest_by_type.get("VALUATION")
    required.append(
        {
            "document_type": "VALUATION",
            "required": False,
            "present": bool(valuation),
            "version_number": valuation.version_number if valuation else None,
            "analysis_status": valuation.analysis_status if valuation else None,
            "filename": valuation.original_filename if valuation else None,
        }
    )
    missing = [
        item["document_type"]
        for item in required
        if item["required"] and not item["present"]
    ]
    return {
        "documents": required,
        "complete": not missing,
        "missing": missing,
        "sources": dict(source_counts),
        "external_references": sorted(references),
        "reference_consistent": len(references) <= 1,
    }

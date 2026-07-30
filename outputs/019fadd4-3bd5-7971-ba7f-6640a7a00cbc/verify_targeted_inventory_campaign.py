#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from backend import models
from backend.database import SessionLocal


CAMPAIGN_REFERENCE = "INV-CIBLE-20260729-85"


def main() -> int:
    data_file = Path("/tmp/mmg-stock-followup-data-20260729.json")
    payload = json.loads(data_file.read_text(encoding="utf-8"))
    target_references = {
        str(item["full_reference"]).strip()
        for item in payload.get("targeted_inventory", [])
    }

    db = SessionLocal()
    try:
        session = (
            db.query(models.InventorySession)
            .filter_by(reference=CAMPAIGN_REFERENCE)
            .one()
        )
        lines = (
            db.query(models.InventoryCountLine)
            .filter_by(session_id=session.id)
            .all()
        )
        variant_ids = {line.variant_id for line in lines}
        variants = (
            db.query(models.ProductVariant)
            .filter(models.ProductVariant.id.in_(variant_ids))
            .all()
        )
        references_by_id = {variant.id: variant.reference for variant in variants}
        line_references = {
            references_by_id[line.variant_id]
            for line in lines
            if line.variant_id in references_by_id
        }
        expected_mismatches = []
        for line in lines:
            quant = (
                db.query(models.StockQuant)
                .filter_by(
                    variant_id=line.variant_id,
                    location_id=line.location_id,
                )
                .one_or_none()
            )
            current_quantity = float(quant.quantity or 0) if quant else 0.0
            if abs(current_quantity - float(line.expected_quantity or 0)) > 0.000001:
                expected_mismatches.append(
                    {
                        "reference": references_by_id.get(line.variant_id),
                        "expected": float(line.expected_quantity or 0),
                        "current": current_quantity,
                    }
                )

        draft_placeholders = (
            db.query(models.Product)
            .filter(
                models.Product.reference_base.in_(target_references),
                models.Product.catalog_status == "DRAFT",
                models.Product.name.like("[COMPTAGE]%"),
            )
            .count()
        )
        adjustment_moves = (
            db.query(models.StockMove)
            .filter_by(
                document_type="inventory_session",
                document_reference=CAMPAIGN_REFERENCE,
            )
            .count()
        )
        result = {
            "session_id": session.id,
            "reference": session.reference,
            "name": session.name,
            "status": session.status,
            "location_id": session.location_id,
            "zone_locked": session.zone_locked,
            "blind_counting": session.blind_counting,
            "line_count": len(lines),
            "distinct_variant_count": len(variant_ids),
            "status_counts": dict(Counter(line.status for line in lines)),
            "location_ids": sorted({line.location_id for line in lines}),
            "missing_references": sorted(target_references - line_references),
            "extra_references": sorted(line_references - target_references),
            "expected_quantity_mismatches": expected_mismatches,
            "draft_placeholders": draft_placeholders,
            "adjustment_moves": adjustment_moves,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))

        valid = (
            len(target_references) == 85
            and len(lines) == 85
            and len(variant_ids) == 85
            and result["status_counts"] == {"pending": 85}
            and result["location_ids"] == [5]
            and not result["missing_references"]
            and not result["extra_references"]
            and not expected_mismatches
            and session.status == "draft"
            and session.location_id == 5
            and session.blind_counting
            and not session.zone_locked
            and draft_placeholders == 15
            and adjustment_moves == 0
        )
        return 0 if valid else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

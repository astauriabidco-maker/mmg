#!/usr/bin/env python3
"""Remise contrôlée du stock physique interne à zéro.

Usage recommandé en production :

    python scripts/reset_stock_to_zero.py --dry-run
    python scripts/reset_stock_to_zero.py --apply --confirm RESET_STOCK_TO_ZERO

Le script ne fait pas d'UPDATE brutal des quantités : chaque quant interne
non nul passe par InventoryService.move_stock vers/depuis Virtual/Inventory,
ce qui crée des mouvements d'audit. Les caches ProductVariant.quantity_in_stock
sont ensuite resynchronisés à partir des quants internes.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import models  # noqa: E402
from backend.database import SessionLocal  # noqa: E402
from backend.services.stock_service import InventoryService  # noqa: E402


CONFIRMATION = "RESET_STOCK_TO_ZERO"


@dataclass
class ResetPlan:
    batch_reference: str
    internal_locations: int
    non_zero_quants: int
    positive_quants: int
    negative_quants: int
    affected_variants: int
    total_positive_quantity: float
    total_negative_quantity: float
    active_reservations: int
    cache_variants_non_zero: int
    apply: bool


def _active_reservations_count(db) -> int:
    return (
        db.query(models.StockReservation)
        .filter(models.StockReservation.status == "reserved")
        .count()
    )


def _non_zero_internal_quants(db):
    return (
        db.query(models.StockQuant)
        .join(models.StockLocation, models.StockQuant.location_id == models.StockLocation.id)
        .filter(
            models.StockLocation.usage == "internal",
            models.StockLocation.is_active == True,  # noqa: E712
            models.StockQuant.quantity != 0,
        )
        .order_by(models.StockQuant.variant_id, models.StockQuant.location_id)
        .all()
    )


def _build_plan(db, *, batch_reference: str, apply: bool) -> ResetPlan:
    quants = _non_zero_internal_quants(db)
    positive = [quant for quant in quants if float(quant.quantity or 0) > 0]
    negative = [quant for quant in quants if float(quant.quantity or 0) < 0]
    internal_location_count = (
        db.query(models.StockLocation)
        .filter(
            models.StockLocation.usage == "internal",
            models.StockLocation.is_active == True,  # noqa: E712
        )
        .count()
    )
    cache_variants_non_zero = (
        db.query(models.ProductVariant)
        .filter(models.ProductVariant.quantity_in_stock != 0)
        .count()
    )
    return ResetPlan(
        batch_reference=batch_reference,
        internal_locations=internal_location_count,
        non_zero_quants=len(quants),
        positive_quants=len(positive),
        negative_quants=len(negative),
        affected_variants=len({quant.variant_id for quant in quants}),
        total_positive_quantity=sum(float(quant.quantity or 0) for quant in positive),
        total_negative_quantity=sum(float(quant.quantity or 0) for quant in negative),
        active_reservations=_active_reservations_count(db),
        cache_variants_non_zero=cache_variants_non_zero,
        apply=apply,
    )


def reset_stock_to_zero(
    *,
    apply: bool,
    confirm: Optional[str],
    author: str,
    allow_active_reservations: bool,
    reason: str,
) -> dict:
    batch_reference = f"RST-STOCK-ZERO-{time.strftime('%Y%m%d-%H%M%S')}"
    db = SessionLocal()
    try:
        plan = _build_plan(db, batch_reference=batch_reference, apply=apply)
        if not apply:
            return {"plan": asdict(plan), "result": {"created_moves": 0, "synced_variants": 0}}

        if confirm != CONFIRMATION:
            raise SystemExit(
                f"Confirmation requise: relancer avec --confirm {CONFIRMATION}. "
                "Aucune écriture effectuée."
            )
        if plan.active_reservations and not allow_active_reservations:
            raise SystemExit(
                f"{plan.active_reservations} réservation(s) active(s) détectée(s). "
                "Annulez/consommez les réservations ou relancez explicitement avec "
                "--allow-active-reservations si vous assumez ce reset."
            )

        inventory_location = InventoryService.get_or_create_location(db, "Virtual/Inventory", "inventory")
        quants_snapshot = [
            (quant.variant_id, quant.location_id, float(quant.quantity or 0))
            for quant in _non_zero_internal_quants(db)
        ]
        created_moves = 0
        for index, (variant_id, location_id, quantity) in enumerate(quants_snapshot, start=1):
            if quantity > 0:
                source_location_id = location_id
                dest_location_id = inventory_location.id
            else:
                source_location_id = inventory_location.id
                dest_location_id = location_id
            InventoryService.move_stock(
                db,
                variant_id=variant_id,
                quantity=abs(quantity),
                source_location_id=source_location_id,
                dest_location_id=dest_location_id,
                reference=f"{batch_reference}-{index:05d}",
                notes=f"{reason} Quantité avant reset: {quantity:g}.",
                author=author,
                source_screen="ops.reset_stock_to_zero",
                document_type="stock_reset",
                document_reference=batch_reference,
                business_reason=reason,
                allow_negative_source=True,
            )
            created_moves += 1

        variant_ids = [variant_id for (variant_id,) in db.query(models.ProductVariant.id).all()]
        for variant_id in variant_ids:
            InventoryService.sync_variant_internal_stock(db, variant_id)

        db.commit()
        final_plan = _build_plan(db, batch_reference=batch_reference, apply=True)
        return {
            "plan": asdict(plan),
            "result": {
                "created_moves": created_moves,
                "synced_variants": len(variant_ids),
                "remaining_non_zero_quants": final_plan.non_zero_quants,
                "remaining_cache_variants_non_zero": final_plan.cache_variants_non_zero,
            },
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Remet les stocks physiques internes à zéro avec audit.")
    parser.add_argument("--apply", action="store_true", help="Applique réellement la remise à zéro.")
    parser.add_argument("--dry-run", action="store_true", help="Prévisualise sans écrire. Mode par défaut.")
    parser.add_argument("--confirm", help=f"Valeur obligatoire en apply: {CONFIRMATION}")
    parser.add_argument("--author", default="ops-reset-stock", help="Auteur inscrit sur les mouvements.")
    parser.add_argument(
        "--allow-active-reservations",
        action="store_true",
        help="Autorise le reset malgré des réservations actives. À éviter sauf décision métier explicite.",
    )
    parser.add_argument(
        "--reason",
        default="Remise à zéro avant mise en production inventaire",
        help="Motif métier inscrit dans les mouvements.",
    )
    args = parser.parse_args()

    payload = reset_stock_to_zero(
        apply=bool(args.apply and not args.dry_run),
        confirm=args.confirm,
        author=args.author,
        allow_active_reservations=args.allow_active_reservations,
        reason=args.reason.strip() or "Remise à zéro stock",
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime
from typing import Iterable

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from .. import models
from scripts.import_workshop_debits import DebitRecord, StockMatch, build_summary, consolidate_records


ACTIVE_RESERVATION_STATUS = "reserved"


def get_or_create_location(db: Session, name: str, usage: str) -> models.StockLocation:
    location = db.query(models.StockLocation).filter_by(name=name, usage=usage).first()
    if location:
        return location
    location = models.StockLocation(name=name, usage=usage, is_active=True)
    db.add(location)
    db.flush()
    return location


def find_variant(db: Session, record: DebitRecord) -> models.ProductVariant | None:
    supplier_prefixed = f"{record.supplier}:{record.reference}"
    return (
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


def active_reserved_quantity(db: Session, variant_id: int) -> float:
    lines = (
        db.query(models.StockReservationLine)
        .join(models.StockReservation)
        .filter(
            models.StockReservationLine.variant_id == variant_id,
            models.StockReservationLine.status == ACTIVE_RESERVATION_STATUS,
            models.StockReservation.status == ACTIVE_RESERVATION_STATUS,
        )
        .all()
    )
    return float(sum(line.reserved_quantity or 0 for line in lines))


def physical_quantity(db: Session, variant_id: int, source_location_id: int) -> float:
    quant = db.query(models.StockQuant).filter_by(variant_id=variant_id, location_id=source_location_id).first()
    return float(quant.quantity if quant else 0)


def preview_records(db: Session, records: Iterable[DebitRecord], source_location: str = "WH/Stock") -> list[StockMatch]:
    source = db.query(models.StockLocation).filter_by(name=source_location, usage="internal").first()
    matches: list[StockMatch] = []
    for record in consolidate_records(list(records)):
        variant = find_variant(db, record)
        reserved = 0.0
        available = 0.0
        if variant and source:
            physical = physical_quantity(db, variant.id, source.id)
            reserved = active_reserved_quantity(db, variant.id)
            available = max(physical - reserved, 0)
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


def build_preview_payload(db: Session, records: list[DebitRecord], issues: list, source_location: str = "WH/Stock") -> dict:
    matches = preview_records(db, records, source_location) if records else []
    summary = build_summary(records, issues)
    summary["stock_match_status"] = dict(sorted(Counter(match.status for match in matches).items()))
    return {
        "summary": summary,
        "issues": [asdict(issue) for issue in issues],
        "records": [asdict(record) for record in consolidate_records(records)],
        "stock_matches": [match.__dict__ for match in matches],
    }


def create_reservation(
    db: Session,
    records: list[DebitRecord],
    source_label: str,
    created_by: str,
    source_location: str = "WH/Stock",
    order_reference: str | None = None,
    notes: str | None = None,
    allow_missing: bool = False,
    allow_shortage: bool = False,
) -> models.StockReservation:
    source = get_or_create_location(db, source_location, "internal")
    consolidated = consolidate_records(records)
    matches = preview_records(db, consolidated, source_location)
    missing = [match for match in matches if match.status == "not_found"]
    shortages = [match for match in matches if match.status == "shortage"]
    if missing and not allow_missing:
        raise ValueError("Références inconnues: " + ", ".join(f"{m.supplier}/{m.reference}" for m in missing[:10]))
    if shortages and not allow_shortage:
        raise ValueError("Stock insuffisant: " + ", ".join(f"{m.supplier}/{m.reference}" for m in shortages[:10]))

    project_reference = next((record.project_reference for record in consolidated if record.project_reference), None)
    reference = f"RSV-ATELIER-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    reservation = models.StockReservation(
        reference=reference,
        order_reference=order_reference or project_reference,
        project_reference=project_reference,
        source_label=source_label,
        status=ACTIVE_RESERVATION_STATUS,
        notes=notes,
        created_by=created_by,
    )
    db.add(reservation)
    db.flush()

    for record, match in zip(consolidated, matches):
        variant = find_variant(db, record)
        status = match.status
        reserved_quantity = record.quantity if status == "ok" else 0.0
        if status == "shortage" and allow_shortage:
            reserved_quantity = max(match.available_quantity, 0)
        db.add(
            models.StockReservationLine(
                reservation_id=reservation.id,
                variant_id=variant.id if variant else None,
                supplier=record.supplier,
                supplier_reference=record.reference,
                designation=record.designation,
                unit=record.unit,
                requested_quantity=record.quantity,
                reserved_quantity=reserved_quantity,
                consumed_quantity=0,
                available_at_reservation=match.available_quantity,
                status=ACTIVE_RESERVATION_STATUS if reserved_quantity > 0 else status,
                source=record.source,
            )
        )

    db.flush()
    return reservation


def consume_reservation(
    db: Session,
    reservation: models.StockReservation,
    source_location: str = "WH/Stock",
    dest_location: str = "Production Ateliers",
    author: str = "Système",
) -> dict[str, int]:
    if reservation.status != ACTIVE_RESERVATION_STATUS:
        return {"created_moves": 0, "consumed_lines": 0}

    source = get_or_create_location(db, source_location, "internal")
    dest = get_or_create_location(db, dest_location, "production")
    now_ref = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    stats = {"created_moves": 0, "consumed_lines": 0}

    for line in reservation.lines:
        if line.status != ACTIVE_RESERVATION_STATUS or not line.variant_id or (line.reserved_quantity or 0) <= 0:
            continue
        src_quant = db.query(models.StockQuant).filter_by(variant_id=line.variant_id, location_id=source.id).first()
        current_qty = float(src_quant.quantity if src_quant else 0)
        if current_qty < line.reserved_quantity:
            raise ValueError(
                f"Stock insuffisant au débit réel pour {line.supplier_reference}: {current_qty:g} < {line.reserved_quantity:g}"
            )
        if not src_quant:
            src_quant = models.StockQuant(variant_id=line.variant_id, location_id=source.id, quantity=0)
            db.add(src_quant)
            db.flush()

        dest_quant = db.query(models.StockQuant).filter_by(variant_id=line.variant_id, location_id=dest.id).first()
        if not dest_quant:
            dest_quant = models.StockQuant(variant_id=line.variant_id, location_id=dest.id, quantity=0)
            db.add(dest_quant)
            db.flush()

        src_quant.quantity -= line.reserved_quantity
        dest_quant.quantity += line.reserved_quantity
        line.consumed_quantity = line.reserved_quantity
        line.status = "consumed"
        if line.variant:
            line.variant.quantity_in_stock = (line.variant.quantity_in_stock or 0) - line.reserved_quantity

        db.add(
            models.StockMove(
                reference=f"DEBIT-ATELIER-{now_ref}",
                variant_id=line.variant_id,
                location_id=source.id,
                location_dest_id=dest.id,
                quantity=line.reserved_quantity,
                state="done",
                notes=f"Consommation réservation {reservation.reference}",
                author=author,
            )
        )
        stats["created_moves"] += 1
        stats["consumed_lines"] += 1

    if stats["consumed_lines"]:
        reservation.status = "consumed"
        reservation.consumed_at = datetime.utcnow()
    return stats


def consume_reservations_for_order(db: Session, order_reference: str, station_code: str, author: str = "Système") -> dict[str, int]:
    if "DEBIT" not in station_code.upper():
        return {"created_moves": 0, "consumed_lines": 0, "reservations": 0}

    reservations = (
        db.query(models.StockReservation)
        .options(joinedload(models.StockReservation.lines).joinedload(models.StockReservationLine.variant))
        .filter(
            models.StockReservation.status == ACTIVE_RESERVATION_STATUS,
            or_(
                models.StockReservation.order_reference == order_reference,
                models.StockReservation.project_reference == order_reference,
            ),
        )
        .all()
    )
    total = {"created_moves": 0, "consumed_lines": 0, "reservations": len(reservations)}
    for reservation in reservations:
        stats = consume_reservation(db, reservation, author=author)
        total["created_moves"] += stats["created_moves"]
        total["consumed_lines"] += stats["consumed_lines"]
    return total

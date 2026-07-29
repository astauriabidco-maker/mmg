from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from .. import models
from ..core.time import utcnow
from .document_sequences import next_number
from .stock_reservations import (
    ACTIVE_RESERVATION_STATUS,
    assert_consumable_at_location,
    assert_technical_launch_authorized,
    resolve_reservation_location,
)
from .stock_service import InventoryService


OPEN_PREPARATION_STATUSES = {"draft", "ready"}


def load_preparation(db: Session, preparation_id: int, *, for_update: bool = False) -> models.WorkshopPreparation | None:
    query = (
        db.query(models.WorkshopPreparation)
        .options(
            joinedload(models.WorkshopPreparation.lines)
            .joinedload(models.WorkshopPreparationLine.variant)
            .joinedload(models.ProductVariant.product),
            joinedload(models.WorkshopPreparation.reservation)
            .joinedload(models.StockReservation.lines),
            joinedload(models.WorkshopPreparation.source_location),
            joinedload(models.WorkshopPreparation.destination_location),
        )
        .filter(models.WorkshopPreparation.id == preparation_id)
    )
    if for_update:
        query = query.with_for_update()
    return query.first()


def create_preparation(
    db: Session,
    *,
    reservation: models.StockReservation,
    destination_location_id: int | None,
    notes: str | None,
    author: str,
) -> models.WorkshopPreparation:
    if reservation.status != ACTIVE_RESERVATION_STATUS:
        raise ValueError("Seule une réservation atelier active peut être préparée.")
    if reservation.source_label in {"devis libre", "devis_libre"}:
        raise ValueError("Une réservation commerciale ne peut pas créer un bon de préparation atelier.")

    existing = (
        db.query(models.WorkshopPreparation)
        .filter(models.WorkshopPreparation.reservation_id == reservation.id)
        .first()
    )
    if existing:
        return existing

    source = resolve_reservation_location(db, reservation)
    destination = (
        db.query(models.StockLocation)
        .filter(
            models.StockLocation.id == destination_location_id,
            models.StockLocation.is_active == True,
        )
        .first()
        if destination_location_id
        else InventoryService.get_or_create_location(db, "ATELIER/Préparation", "internal")
    )
    if not destination:
        raise ValueError("Zone de préparation atelier introuvable.")
    if destination.usage != "internal":
        raise ValueError("La zone de préparation atelier doit être un emplacement interne.")
    if destination.id == source.id:
        raise ValueError("La zone atelier doit être différente de l'emplacement de prélèvement.")

    preparation = models.WorkshopPreparation(
        reference=next_number(db, "workshop_preparation"),
        reservation_id=reservation.id,
        sale_order_id=reservation.sale_order_id,
        production_order_id=reservation.production_order_id,
        source_location_id=source.id,
        destination_location_id=destination.id,
        status="draft",
        notes=(notes or "").strip() or None,
        created_by=author,
    )
    db.add(preparation)
    db.flush()

    for reservation_line in reservation.lines:
        quantity = float(reservation_line.reserved_quantity or 0)
        if reservation_line.status != ACTIVE_RESERVATION_STATUS or not reservation_line.variant_id or quantity <= 0:
            continue
        db.add(
            models.WorkshopPreparationLine(
                preparation_id=preparation.id,
                reservation_line_id=reservation_line.id,
                variant_id=reservation_line.variant_id,
                planned_quantity=quantity,
                prepared_quantity=0,
                transferred_quantity=0,
                returned_quantity=0,
                status="pending",
            )
        )
    db.flush()
    if not preparation.lines:
        raise ValueError("La réservation ne contient aucune ligne stockable à préparer.")
    return load_preparation(db, preparation.id) or preparation


def update_prepared_quantity(
    db: Session,
    preparation: models.WorkshopPreparation,
    line_id: int,
    prepared_quantity: float,
) -> models.WorkshopPreparation:
    if preparation.status not in OPEN_PREPARATION_STATUSES:
        raise ValueError("Ce bon n'est plus modifiable.")
    line = next((item for item in preparation.lines if item.id == line_id), None)
    if not line:
        raise ValueError("Ligne de préparation introuvable.")

    quantity = float(prepared_quantity or 0)
    if quantity < 0:
        raise ValueError("La quantité préparée ne peut pas être négative.")
    if quantity > float(line.planned_quantity or 0) + 1e-9:
        raise ValueError("La quantité préparée dépasse la quantité prévue.")

    line.prepared_quantity = quantity
    line.status = "prepared" if abs(quantity - float(line.planned_quantity or 0)) <= 1e-9 else "pending"
    preparation.status = (
        "ready"
        if preparation.lines and all(item.status == "prepared" for item in preparation.lines)
        else "draft"
    )
    db.flush()
    return preparation


def hand_over_preparation(
    db: Session,
    preparation: models.WorkshopPreparation,
    *,
    author: str,
) -> dict[str, int]:
    if preparation.status == "handed_over":
        return {"created_moves": 0, "transferred_lines": 0}
    if preparation.status != "ready":
        raise ValueError("Toutes les lignes doivent être préparées avant la remise à l'atelier.")

    reservation = preparation.reservation
    if not reservation or reservation.status != ACTIVE_RESERVATION_STATUS:
        raise ValueError("La réservation liée n'est plus active.")
    if reservation.location_id != preparation.source_location_id:
        raise ValueError("L'emplacement de la réservation a changé depuis la création du bon.")

    assert_technical_launch_authorized(db, reservation)
    assert_consumable_at_location(db, reservation, preparation.source_location)
    stats = {"created_moves": 0, "transferred_lines": 0}
    for line in preparation.lines:
        quantity = float(line.prepared_quantity or 0)
        if line.status != "prepared" or quantity <= 0:
            raise ValueError("Le bon contient une ligne incomplète.")
        InventoryService.move_stock(
            db,
            variant_id=line.variant_id,
            source_location_id=preparation.source_location_id,
            dest_location_id=preparation.destination_location_id,
            quantity=quantity,
            reference=f"{preparation.reference}-{line.id:03d}",
            notes=f"Remise atelier | Bon {preparation.reference} | Réservation {reservation.reference}",
            author=author,
            source_screen="stock.workshop_preparation",
            document_type="workshop_preparation",
            document_reference=preparation.reference,
            business_reason="Mise à disposition physique pour l'atelier",
        )
        line.transferred_quantity = quantity
        line.status = "handed_over"
        stats["created_moves"] += 1
        stats["transferred_lines"] += 1

    reservation.location_id = preparation.destination_location_id
    preparation.status = "handed_over"
    preparation.handed_over_by = author
    preparation.handed_over_at = utcnow()
    db.flush()
    return stats


def return_preparation(
    db: Session,
    preparation: models.WorkshopPreparation,
    *,
    author: str,
) -> dict[str, int]:
    if preparation.status == "returned":
        return {"created_moves": 0, "returned_lines": 0}
    if preparation.status != "handed_over":
        raise ValueError("Seul un bon remis et non consommé peut être retourné au magasin.")
    reservation = preparation.reservation
    if not reservation or reservation.status != ACTIVE_RESERVATION_STATUS:
        raise ValueError("La réservation liée n'est plus active.")

    stats = {"created_moves": 0, "returned_lines": 0}
    for line in preparation.lines:
        quantity = float(line.transferred_quantity or 0)
        if line.status != "handed_over" or quantity <= 0:
            continue
        InventoryService.move_stock(
            db,
            variant_id=line.variant_id,
            source_location_id=preparation.destination_location_id,
            dest_location_id=preparation.source_location_id,
            quantity=quantity,
            reference=f"RETOUR-{preparation.reference}-{line.id:03d}",
            notes=f"Retour magasin avant débit | Bon {preparation.reference}",
            author=author,
            source_screen="stock.workshop_preparation_return",
            document_type="workshop_preparation",
            document_reference=preparation.reference,
            business_reason="Retour intégral de la préparation atelier",
        )
        line.returned_quantity = quantity
        line.status = "returned"
        stats["created_moves"] += 1
        stats["returned_lines"] += 1

    reservation.location_id = preparation.source_location_id
    preparation.status = "returned"
    preparation.returned_by = author
    preparation.returned_at = utcnow()
    db.flush()
    return stats


def cancel_preparation(db: Session, preparation: models.WorkshopPreparation) -> None:
    if preparation.status == "cancelled":
        return
    if preparation.status not in OPEN_PREPARATION_STATUSES:
        raise ValueError("Un bon déjà remis doit d'abord être retourné au magasin.")
    preparation.status = "cancelled"
    for line in preparation.lines:
        line.status = "cancelled"
    db.flush()

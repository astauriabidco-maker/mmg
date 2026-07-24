from __future__ import annotations

import logging
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from typing import Iterable

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from .. import models
from .stock_service import InventoryService
from scripts.import_workshop_debits import DebitRecord, StockMatch, build_summary, consolidate_records
from ..core.time import utcnow


logger = logging.getLogger(__name__)


ACTIVE_RESERVATION_STATUS = "reserved"
RESERVABLE_SALE_STATUSES = {"VALIDATED", "IN_DESIGN", "READY_FOR_PROD", "IN_PRODUCTION"}
COMMERCIAL_RESERVATION_PREFIX = "RSV-COM"
ALU_SUPPLIERS = {"CORTIZO", "SEPALUMIC", "TECHNAL/HYDRO", "TECHNAL", "HYDRO"}
PVC_SUPPLIERS = {"VEKA", "KOMMERLING", "KÖMMERLING", "REHAU", "DECEUNINCK"}
DEFAULT_INTERNAL_LOCATION_NAME = "WH/Stock"


class InsufficientStockAtConsumptionError(ValueError):
    """Disponible insuffisant sur l'emplacement ancré au moment de consommer.

    Levée par le re-contrôle transactionnel de la consommation : le stock a
    été prélevé par un autre flux (POS, vente, ajustement…) entre la
    réservation et le débit. Mappée en HTTP 409 par les routeurs."""


def get_default_internal_location(db: Session) -> models.StockLocation:
    """Emplacement interne principal : « WH/Stock » actif, sinon premier interne actif.

    Convention documentée dans la migration ``c6e1a8d3f045`` (backfill des
    réservations historiques).
    """
    location = (
        db.query(models.StockLocation)
        .filter_by(name=DEFAULT_INTERNAL_LOCATION_NAME, usage="internal", is_active=True)
        .first()
    )
    if location:
        return location
    location = (
        db.query(models.StockLocation)
        .filter_by(usage="internal", is_active=True)
        .order_by(models.StockLocation.id.asc())
        .first()
    )
    if location:
        return location
    return get_or_create_location(db, DEFAULT_INTERNAL_LOCATION_NAME, "internal")


def resolve_reservation_location(db: Session, reservation: models.StockReservation) -> models.StockLocation:
    """Emplacement de prélèvement d'une réservation : son ancre, sinon le principal.

    Les réservations historiques sans ancre (location_id NULL, base non
    migrée ou emplacement supprimé) retombent sur l'emplacement interne
    principal — le comportement d'avant l'ancrage.
    """
    if reservation.location_id:
        location = db.query(models.StockLocation).filter_by(id=reservation.location_id).first()
        if location:
            return location
    return get_default_internal_location(db)


def infer_material_from_records(records: Iterable[DebitRecord]) -> str | None:
    records = list(records)
    values = " ".join(
        " ".join([record.supplier, record.reference, record.designation, record.color or "", record.source])
        for record in records
    ).upper()
    suppliers = {record.supplier.upper() for record in records}
    if suppliers.intersection(ALU_SUPPLIERS) or any(token in values for token in [" ALU", "ALUMINIUM", "CORTIZO", "SEPALUMIC"]):
        return "ALU"
    if suppliers.intersection(PVC_SUPPLIERS) or any(token in values for token in [" PVC", "KOMMERLING", "KÖMMERLING", "REHAU"]):
        return "PVC"
    return None


def infer_material_from_sale(sale: models.SaleOrder) -> str | None:
    text = " ".join(line.description or "" for line in sale.lines).upper()
    if any(token in text for token in [" PVC", "PVC ", "KOMMERLING", "KÖMMERLING", "REHAU"]):
        return "PVC"
    if any(token in text for token in [" ALU", "ALUMINIUM", "CORTIZO", "SEPALUMIC", "TECHNAL"]):
        return "ALU"
    return None


def validate_workflow_context(
    db: Session,
    records: list[DebitRecord],
    sale_order_id: int | None = None,
    production_order_id: int | None = None,
) -> tuple[models.SaleOrder | None, models.Order | None, list[dict]]:
    issues: list[dict] = []
    sale = None
    production_order = None

    if sale_order_id:
        sale = db.query(models.SaleOrder).filter(models.SaleOrder.id == sale_order_id).first()
        if not sale:
            raise ValueError("Devis introuvable.")
        if sale.status not in RESERVABLE_SALE_STATUSES:
            raise ValueError(
                f"Devis {sale.reference} au statut {sale.status}; réservation autorisée seulement après validation."
            )
        duplicate = (
            db.query(models.StockReservation)
            .filter(
                models.StockReservation.sale_order_id == sale.id,
                models.StockReservation.status == ACTIVE_RESERVATION_STATUS,
            )
            .first()
        )
        if duplicate:
            raise ValueError(f"Une réservation active existe déjà pour {sale.reference}: {duplicate.reference}.")

    if production_order_id:
        production_order = db.query(models.Order).filter(models.Order.id == production_order_id).first()
        if not production_order:
            raise ValueError("Ordre de production introuvable.")

    if not sale and not production_order:
        raise ValueError("La réservation doit être liée à un devis validé ou à un ordre de production.")

    file_material = infer_material_from_records(records)
    expected_material = None
    if production_order:
        expected_material = production_order.material.value if hasattr(production_order.material, "value") else production_order.material
    elif sale:
        expected_material = infer_material_from_sale(sale)

    if file_material and expected_material and file_material != expected_material:
        raise ValueError(f"Incohérence matière: fichier {file_material}, dossier {expected_material}.")
    if file_material and not expected_material:
        issues.append(
            {
                "severity": "warning",
                "code": "material_not_confirmed",
                "message": f"Matière détectée {file_material}, mais le devis ne permet pas de confirmer la matière.",
            }
        )

    return sale, production_order, issues


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


def active_reserved_quantity(db: Session, variant_id: int, location_id: int | None = None) -> float:
    query = (
        db.query(models.StockReservationLine)
        .join(models.StockReservation)
        .filter(
            models.StockReservationLine.variant_id == variant_id,
            models.StockReservationLine.status == ACTIVE_RESERVATION_STATUS,
            models.StockReservation.status == ACTIVE_RESERVATION_STATUS,
        )
    )
    if location_id is not None:
        # Réservations historiques sans ancre (location_id NULL) : elles pèsent
        # sur tous les emplacements — hypothèse conservatrice qui évite toute
        # sur-réservation tant que le backfill n'a pas tourné.
        query = query.filter(
            or_(
                models.StockReservation.location_id == location_id,
                models.StockReservation.location_id.is_(None),
            )
        )
    lines = query.all()
    return float(sum(line.reserved_quantity or 0 for line in lines))


def physical_quantity_all_internal(db: Session, variant: models.ProductVariant) -> float:
    """Stock physique = Σ des quants internes actifs (source de vérité).

    Divergence détectée (cache ``quantity_in_stock`` > 0 sans aucun quant) :
    on logue un warning explicite et on retourne la somme des quants (0). Le
    cache n'est plus utilisé en secours : le masquer faisait croire à un
    stock disponible inexistant. Les flux existants ne sont pas cassés — la
    valeur retournée reste un float — mais la divergence devient visible dans
    les logs et dans les disponibilités affichées.
    """
    quantity = (
        db.query(models.StockQuant)
        .join(models.StockLocation, models.StockQuant.location_id == models.StockLocation.id)
        .filter(
            models.StockQuant.variant_id == variant.id,
            models.StockLocation.usage == "internal",
            models.StockLocation.is_active == True,
        )
        .with_entities(models.StockQuant.quantity)
        .all()
    )
    total = float(sum(row[0] or 0 for row in quantity))
    cache = float(variant.quantity_in_stock or 0)
    if total == 0 and cache > 0:
        logger.warning(
            "Divergence stock variante #%s (%s) : cache quantity_in_stock=%g mais aucun quant interne. "
            "La somme des quants (0) fait foi ; lancez un ajustement d'inventaire pour régulariser.",
            variant.id,
            variant.reference,
            cache,
        )
    return total


def available_quantity_for_variant(db: Session, variant: models.ProductVariant) -> tuple[float, float, float]:
    physical = physical_quantity_all_internal(db, variant)
    reserved = active_reserved_quantity(db, variant.id)
    return physical, reserved, max(physical - reserved, 0.0)


def annotate_variant_availability(db: Session, variant: models.ProductVariant | None) -> None:
    if not variant:
        return
    physical, reserved, available = available_quantity_for_variant(db, variant)
    variant.quantity_in_stock = physical
    variant.reserved_quantity = reserved
    variant.available_quantity = available


def annotate_sale_availability(db: Session, sale: models.SaleOrder) -> None:
    for line in sale.lines or []:
        if not line.line_type:
            line.line_type = "STOCK_ITEM" if line.variant_id else "SERVICE"
        if line.variant:
            annotate_variant_availability(db, line.variant)
            line.reserved_quantity = line.variant.reserved_quantity
            line.available_quantity = line.variant.available_quantity
        else:
            line.reserved_quantity = 0.0
            line.available_quantity = 0.0


def physical_quantity(db: Session, variant_id: int, source_location_id: int) -> float:
    quant = db.query(models.StockQuant).filter_by(variant_id=variant_id, location_id=source_location_id).first()
    return float(quant.quantity if quant else 0)


def available_quantity_at_location(db: Session, variant_id: int, location_id: int) -> tuple[float, float, float]:
    """Disponible FERME sur un emplacement : physique de l'emplacement - réservé actif de l'emplacement."""
    physical = physical_quantity(db, variant_id, location_id)
    reserved = active_reserved_quantity(db, variant_id, location_id=location_id)
    return physical, reserved, max(physical - reserved, 0.0)


def preview_records(db: Session, records: Iterable[DebitRecord], source_location: str = "WH/Stock") -> list[StockMatch]:
    source = db.query(models.StockLocation).filter_by(name=source_location, usage="internal").first()
    matches: list[StockMatch] = []
    for record in consolidate_records(list(records)):
        variant = find_variant(db, record)
        reserved = 0.0
        available = 0.0
        if variant and source:
            # Fermeté : le disponible est évalué sur L'EMPLACEMENT source de la
            # réservation, plus sur la somme de tous les emplacements internes.
            _physical, reserved, available = available_quantity_at_location(db, variant.id, source.id)
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


def build_preview_payload(
    db: Session,
    records: list[DebitRecord],
    issues: list,
    source_location: str = "WH/Stock",
    sale_order_id: int | None = None,
    production_order_id: int | None = None,
) -> dict:
    matches = preview_records(db, records, source_location) if records else []
    summary = build_summary(records, issues)
    summary["stock_match_status"] = dict(sorted(Counter(match.status for match in matches).items()))
    workflow_issues = []
    if records and (sale_order_id or production_order_id):
        try:
            _sale, _production_order, workflow_issues = validate_workflow_context(
                db,
                records,
                sale_order_id=sale_order_id,
                production_order_id=production_order_id,
            )
        except ValueError as exc:
            workflow_issues = [{"severity": "error", "code": "workflow_context", "message": str(exc)}]
    elif records:
        workflow_issues = [
            {
                "severity": "error",
                "code": "missing_workflow_context",
                "message": "Sélectionner un devis validé ou un ordre de production avant de réserver.",
            }
        ]
    return {
        "summary": summary,
        "issues": [asdict(issue) for issue in issues] + workflow_issues,
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
    sale_order_id: int | None = None,
    production_order_id: int | None = None,
    notes: str | None = None,
    allow_missing: bool = False,
    allow_shortage: bool = False,
) -> models.StockReservation:
    source = get_or_create_location(db, source_location, "internal")
    consolidated = consolidate_records(records)
    if not consolidated:
        raise ValueError("Aucune ligne atelier exploitable dans les fichiers fournis.")
    sale, production_order, _workflow_issues = validate_workflow_context(
        db,
        consolidated,
        sale_order_id=sale_order_id,
        production_order_id=production_order_id,
    )
    matches = preview_records(db, consolidated, source_location)
    missing = [match for match in matches if match.status == "not_found"]
    shortages = [match for match in matches if match.status == "shortage"]
    if missing and not allow_missing:
        raise ValueError("Références inconnues: " + ", ".join(f"{m.supplier}/{m.reference}" for m in missing[:10]))
    if shortages and not allow_shortage:
        raise ValueError("Stock insuffisant: " + ", ".join(f"{m.supplier}/{m.reference}" for m in shortages[:10]))

    project_reference = next((record.project_reference for record in consolidated if record.project_reference), None)
    reference = f"RSV-ATELIER-{utcnow().strftime('%Y%m%d%H%M%S%f')}"
    resolved_order_reference = (
        order_reference
        or (production_order.reference if production_order else None)
        or (sale.reference if sale else None)
        or project_reference
    )
    reservation = models.StockReservation(
        reference=reference,
        sale_order_id=sale.id if sale else None,
        production_order_id=production_order.id if production_order else None,
        order_reference=resolved_order_reference,
        project_reference=project_reference,
        source_label=source_label,
        location_id=source.id,
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


def create_commercial_reservation_for_sale(
    db: Session,
    sale: models.SaleOrder,
    created_by: str = "Système",
) -> models.StockReservation | None:
    duplicate = (
        db.query(models.StockReservation)
        .filter(
            models.StockReservation.sale_order_id == sale.id,
            models.StockReservation.status == ACTIVE_RESERVATION_STATUS,
            models.StockReservation.source_label.in_(["devis libre", "devis_libre"]),
        )
        .first()
    )
    if duplicate:
        return duplicate

    stock_lines = [
        line
        for line in sale.lines
        if (line.line_type or "").upper() == "STOCK_ITEM" and line.variant_id and (line.quantity or 0) > 0
    ]
    if not stock_lines:
        return None

    # Réservation commerciale ancrée sur l'emplacement interne principal : le
    # contrôle de disponibilité porte sur CET emplacement (fermeté), plus sur
    # la somme de tous les emplacements internes.
    location = get_default_internal_location(db)

    shortages = []
    for line in stock_lines:
        variant = line.variant
        if not variant:
            continue
        _physical, _already_reserved, available = available_quantity_at_location(db, variant.id, location.id)
        requested = float(line.quantity or 0)
        if available < requested:
            shortages.append(f"{variant.reference}: {available:g} disponible < {requested:g} demandé")
    if shortages:
        raise ValueError("Stock insuffisant pour le devis libre: " + ", ".join(shortages[:10]))

    reservation = models.StockReservation(
        reference=f"{COMMERCIAL_RESERVATION_PREFIX}-{utcnow().strftime('%Y%m%d%H%M%S%f')}",
        sale_order_id=sale.id,
        order_reference=sale.reference,
        source_label="devis libre",
        location_id=location.id,
        status=ACTIVE_RESERVATION_STATUS,
        notes=f"Réservation commerciale automatique à validation du devis {sale.reference}.",
        created_by=created_by,
    )
    db.add(reservation)
    db.flush()

    for line in stock_lines:
        variant = line.variant
        if not variant:
            continue
        _physical, _already_reserved, available = available_quantity_at_location(db, variant.id, location.id)
        requested = float(line.quantity or 0)
        db.add(
            models.StockReservationLine(
                reservation_id=reservation.id,
                variant_id=variant.id,
                supplier=variant.product.supplier if variant.product else None,
                supplier_reference=variant.supplier_reference or variant.reference,
                designation=line.description,
                unit=variant.product.unit if variant.product else None,
                requested_quantity=requested,
                reserved_quantity=requested,
                consumed_quantity=0.0,
                available_at_reservation=available,
                status=ACTIVE_RESERVATION_STATUS,
                source=f"sale_order_line:{line.id}",
            )
        )

    db.flush()
    return reservation


def _own_active_reserved_quantity(db: Session, reservation_id: int, variant_id: int) -> float:
    lines = (
        db.query(models.StockReservationLine)
        .filter(
            models.StockReservationLine.reservation_id == reservation_id,
            models.StockReservationLine.variant_id == variant_id,
            models.StockReservationLine.status == ACTIVE_RESERVATION_STATUS,
        )
        .all()
    )
    return float(sum(line.reserved_quantity or 0 for line in lines))


def assert_consumable_at_location(db: Session, reservation: models.StockReservation, location: models.StockLocation) -> None:
    """Re-contrôle du disponible réel sur l'emplacement ancré avant consommation.

    Un autre flux (POS, vente, ajustement, inventaire) a pu prélever le stock
    entre la réservation et le débit. On vérifie, agrégé par variante, que le
    physique de l'emplacement couvre le réservé actif des AUTRES réservations
    plus les lignes de celle-ci ; sinon erreur métier explicite (409 côté
    routeurs) plutôt qu'un débit partiel ou un stock incohérent.
    """
    required: dict[int, float] = {}
    labels: dict[int, str] = {}
    for line in reservation.lines:
        if line.status != ACTIVE_RESERVATION_STATUS or not line.variant_id or (line.reserved_quantity or 0) <= 0:
            continue
        required[line.variant_id] = required.get(line.variant_id, 0.0) + float(line.reserved_quantity or 0)
        labels.setdefault(line.variant_id, line.supplier_reference or f"variante #{line.variant_id}")

    for variant_id, quantity in required.items():
        physical = physical_quantity(db, variant_id, location.id)
        reserved_here = active_reserved_quantity(db, variant_id, location_id=location.id)
        # La part réservée par CETTE réservation reste disponible pour elle.
        own = _own_active_reserved_quantity(db, reservation.id, variant_id)
        available = physical - max(reserved_here - own, 0.0)
        if available + 1e-9 < quantity:
            usable = max(available, 0.0)
            missing = quantity - usable
            raise InsufficientStockAtConsumptionError(
                f"Stock insuffisant sur l'emplacement « {location.name} » pour consommer la réservation "
                f"{reservation.reference} : {labels[variant_id]} — disponible {usable:g}, requis {quantity:g} "
                f"(manquant {missing:g}). Le stock a probablement été prélevé par un autre flux entre la "
                f"réservation et la consommation."
            )


def consume_reservation(
    db: Session,
    reservation: models.StockReservation,
    source_location: str | None = None,
    dest_location: str = "Production Ateliers",
    author: str = "Système",
) -> dict[str, int]:
    if reservation.status != ACTIVE_RESERVATION_STATUS:
        return {"created_moves": 0, "consumed_lines": 0}

    preparation = (
        db.query(models.WorkshopPreparation)
        .filter(models.WorkshopPreparation.reservation_id == reservation.id)
        .first()
    )
    if not preparation:
        raise ValueError(
            "Créez et remettez d'abord le bon de préparation atelier avant le débit réel."
        )
    if preparation.status != "handed_over":
        raise ValueError(
            f"Le bon {preparation.reference} doit être entièrement préparé et remis à l'atelier avant le débit réel."
        )

    # Consommation depuis l'emplacement ANCRÉ à la réservation (plus depuis
    # « WH/Stock » en dur). Le paramètre source_location ne sert que de repli
    # explicite pour les réservations historiques sans ancre.
    source = (
        resolve_reservation_location(db, reservation)
        if not source_location
        else get_or_create_location(db, source_location, "internal")
    )
    dest = get_or_create_location(db, dest_location, "production")
    assert_consumable_at_location(db, reservation, source)
    now_ref = utcnow().strftime("%Y%m%d%H%M%S")
    stats = {"created_moves": 0, "consumed_lines": 0}

    for line in reservation.lines:
        if line.status != ACTIVE_RESERVATION_STATUS or not line.variant_id or (line.reserved_quantity or 0) <= 0:
            continue
        line.consumed_quantity = line.reserved_quantity
        line.status = "consumed"

        context_reference = reservation.order_reference or reservation.project_reference or "sans contexte"
        try:
            InventoryService.move_stock(
                db,
                variant_id=line.variant_id,
                source_location_id=source.id,
                dest_location_id=dest.id,
                quantity=line.reserved_quantity,
                reference=f"DEBIT-ATELIER-{now_ref}",
                notes=f"Débit atelier réel | Réservation {reservation.reference} | Contexte {context_reference}",
                author=author,
                source_screen="atelier.debit_reel",
                document_type="stock_reservation",
                document_reference=reservation.reference,
                business_reason=f"Débit réel atelier pour {context_reference}",
            )
        except ValueError as exc:
            raise ValueError(
                f"Stock insuffisant au débit réel pour {line.supplier_reference}: {exc}"
            ) from exc
        stats["created_moves"] += 1
        stats["consumed_lines"] += 1

    if stats["consumed_lines"]:
        reservation.status = "consumed"
        reservation.consumed_at = utcnow()
        preparation.status = "consumed"
        for line in preparation.lines:
            if line.status == "handed_over":
                line.status = "consumed"
    return stats


def consume_commercial_reservation(
    db: Session,
    reservation: models.StockReservation,
    source_location: str | None = None,
    dest_location: str = "Partner/Customer",
    author: str = "Système",
) -> dict[str, int]:
    if reservation.status != ACTIVE_RESERVATION_STATUS:
        return {"created_moves": 0, "consumed_lines": 0}
    if reservation.source_label not in {"devis libre", "devis_libre"}:
        raise ValueError("Cette réservation n'est pas une réservation commerciale de devis libre.")

    source = (
        resolve_reservation_location(db, reservation)
        if not source_location
        else get_or_create_location(db, source_location, "internal")
    )
    dest = get_or_create_location(db, dest_location, "customer")
    assert_consumable_at_location(db, reservation, source)
    now_ref = utcnow().strftime("%Y%m%d%H%M%S")
    stats = {"created_moves": 0, "consumed_lines": 0}

    for line in reservation.lines:
        if line.status != ACTIVE_RESERVATION_STATUS or not line.variant_id or (line.reserved_quantity or 0) <= 0:
            continue

        line.consumed_quantity = line.reserved_quantity
        line.status = "consumed"

        context_reference = reservation.order_reference or reservation.project_reference or "sans contexte"
        try:
            result = InventoryService.move_stock(
                db,
                variant_id=line.variant_id,
                source_location_id=source.id,
                dest_location_id=dest.id,
                quantity=line.reserved_quantity,
                reference=f"SORTIE-CLIENT-{now_ref}",
                notes=f"Sortie client devis libre | Réservation {reservation.reference} | Devis {context_reference}",
                author=author,
                source_screen="sales.customer_delivery",
                document_type="stock_reservation",
                document_reference=reservation.reference,
                business_reason=f"Sortie client devis libre {context_reference}",
            )
        except ValueError as exc:
            raise ValueError(
                f"Stock insuffisant à la sortie client pour {line.supplier_reference}: {exc}"
            ) from exc
        db.add(
            models.ChatterMessage(
                model_name="variant",
                record_id=line.variant_id,
                body=f"Sortie client de {line.reserved_quantity:g} unité(s) depuis la réservation {reservation.reference}.",
                author=author,
                is_system_log=True,
            )
        )
        stats["created_moves"] += 1
        stats["consumed_lines"] += 1

    if stats["consumed_lines"]:
        reservation.status = "consumed"
        reservation.consumed_at = utcnow()
    return stats


def return_commercial_reservation(
    db: Session,
    reservation: models.StockReservation,
    source_location: str = "Partner/Customer",
    dest_location: str | None = None,
    author: str = "Système",
) -> dict[str, int]:
    if reservation.status == "returned":
        return {"created_moves": 0, "returned_lines": 0}
    if reservation.status != "consumed":
        raise ValueError("Seule une réservation commerciale consommée peut être retournée.")
    if reservation.source_label not in {"devis libre", "devis_libre"}:
        raise ValueError("Cette réservation n'est pas une réservation commerciale de devis libre.")

    source = get_or_create_location(db, source_location, "customer")
    # Le retour recrédite l'emplacement ANCRÉ à la réservation (celui d'où le
    # stock est sorti), plus « WH/Stock » en dur ; repli explicite possible.
    dest = (
        get_or_create_location(db, dest_location, "internal")
        if dest_location
        else resolve_reservation_location(db, reservation)
    )
    now_ref = utcnow().strftime("%Y%m%d%H%M%S")
    stats = {"created_moves": 0, "returned_lines": 0}

    for line in reservation.lines:
        returned_quantity = line.consumed_quantity or line.reserved_quantity or 0
        if line.status != "consumed" or not line.variant_id or returned_quantity <= 0:
            continue

        line.status = "returned"

        context_reference = reservation.order_reference or reservation.project_reference or "sans contexte"
        try:
            result = InventoryService.move_stock(
                db,
                variant_id=line.variant_id,
                source_location_id=source.id,
                dest_location_id=dest.id,
                quantity=returned_quantity,
                reference=f"RETOUR-CLIENT-{now_ref}",
                notes=f"Retour client devis libre | Réservation {reservation.reference} | Devis {context_reference}",
                author=author,
                source_screen="sales.customer_return",
                document_type="stock_reservation",
                document_reference=reservation.reference,
                business_reason=f"Retour client devis libre {context_reference}",
            )
        except ValueError as exc:
            raise ValueError(
                f"Stock client insuffisant pour le retour de {line.supplier_reference}: {exc}"
            ) from exc
        db.add(
            models.ChatterMessage(
                model_name="variant",
                record_id=line.variant_id,
                body=f"Retour client de {returned_quantity:g} unité(s) depuis la réservation {reservation.reference}.",
                author=author,
                is_system_log=True,
            )
        )
        stats["created_moves"] += 1
        stats["returned_lines"] += 1

    if stats["returned_lines"]:
        reservation.status = "returned"
        reservation.notes = (
            (reservation.notes or "")
            + f"\nRetour client effectué le {utcnow().strftime('%Y-%m-%d %H:%M:%S')}."
        ).strip()
    return stats


def cancel_reservation(
    db: Session,
    reservation: models.StockReservation,
) -> dict[str, int]:
    if reservation.status != ACTIVE_RESERVATION_STATUS:
        return {"cancelled_lines": 0, "released_quantity": 0}

    preparation = (
        db.query(models.WorkshopPreparation)
        .filter(models.WorkshopPreparation.reservation_id == reservation.id)
        .first()
    )
    if preparation and preparation.status == "handed_over":
        raise ValueError(
            f"Le bon {preparation.reference} a été remis à l'atelier. Retournez-le au magasin avant d'annuler la réservation."
        )

    stats = {"cancelled_lines": 0, "released_quantity": 0}
    for line in reservation.lines:
        if line.status != ACTIVE_RESERVATION_STATUS:
            continue
        stats["released_quantity"] += line.reserved_quantity or 0
        line.status = "cancelled"
        stats["cancelled_lines"] += 1

    reservation.status = "cancelled"
    return stats


def consume_reservations_for_order(db: Session, order_reference: str, station_code: str, author: str = "Système") -> dict[str, int]:
    if "DEBIT" not in station_code.upper():
        return {"created_moves": 0, "consumed_lines": 0, "reservations": 0}

    order = db.query(models.Order).filter(models.Order.reference == order_reference).first()
    reservations = (
        db.query(models.StockReservation)
        .options(joinedload(models.StockReservation.lines).joinedload(models.StockReservationLine.variant))
        .filter(
            models.StockReservation.status == ACTIVE_RESERVATION_STATUS,
            or_(
                models.StockReservation.production_order_id == (order.id if order else None),
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

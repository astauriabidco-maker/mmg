from __future__ import annotations

from collections.abc import Iterable
from enum import Enum
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend import models
from backend.core.time import utcnow
from backend.domain.ontology import (
    DOCUMENT_TYPES,
    STEP_RBAC,
    ontology_as_dict,
    resolve_external_document,
)
from backend.services.stock_reservations import active_reserved_quantity


def _scalar_count(db: Session, model, *criteria) -> int:
    query = db.query(func.count(model.id))
    if criteria:
        query = query.filter(*criteria)
    return int(query.scalar() or 0)


def _group_counts(db: Session, model, column, *criteria) -> dict[str, int]:
    query = db.query(column, func.count(model.id))
    if criteria:
        query = query.filter(*criteria)
    rows = query.group_by(column).all()
    return {
        str(value.value if isinstance(value, Enum) else value if value is not None else "UNKNOWN"): int(count or 0)
        for value, count in rows
    }


def _entity_profile(
    db: Session,
    model,
    *,
    status_column=None,
    criteria: Iterable[Any] = (),
) -> dict[str, Any]:
    filters = tuple(criteria)
    profile: dict[str, Any] = {
        "record_count": _scalar_count(db, model, *filters),
    }
    if status_column is not None:
        profile["status_field"] = status_column.key
        profile["status_counts"] = _group_counts(db, model, status_column, *filters)
    return profile


def _technical_version_profile(
    db: Session,
    canonical_entity: str,
    document_types: tuple[str, ...],
) -> dict[str, Any]:
    criteria = (models.TechnicalDossierVersion.document_type.in_(document_types),)
    profile = _entity_profile(
        db,
        models.TechnicalDossierVersion,
        status_column=models.TechnicalDossierVersion.analysis_status,
        criteria=criteria,
    )
    profile["document_types"] = list(document_types)
    profile["canonical_entity"] = canonical_entity
    return profile


_VAGUE_LOCATION_WORDS = {
    "divers",
    "stock",
    "test",
    "zone",
    "autre",
    "temp",
    "temporary",
    "vrac",
    "inconnu",
    "unknown",
}


def _purchase_location_full_name(db: Session, location: models.StockLocation | None) -> str:
    if not location:
        return ""
    parts = [location.name or ""]
    parent_id = location.parent_id
    while parent_id:
        parent = db.query(models.StockLocation).filter(models.StockLocation.id == parent_id).first()
        if not parent:
            break
        parts.append(parent.name or "")
        parent_id = parent.parent_id
    return " > ".join(reversed([part for part in parts if part]))


def _purchase_location_role(db: Session, location: models.StockLocation | None) -> str:
    if not location:
        return "Inconnu"
    label = f"{location.name or ''} {_purchase_location_full_name(db, location)}".lower()
    if location.usage == "production" or "atelier" in label or "préparation" in label or "preparation" in label:
        return "Zone atelier"
    if "casier" in label or "case" in label or "bac" in label:
        return "Casier final"
    if "rack" in label or "travée" in label or "travee" in label or "étag" in label or "etag" in label:
        return "Rack"
    last_segment = (location.name or "").split("/")[-1].strip().lower()
    if len(last_segment) >= 2 and last_segment[0].isalpha() and last_segment[1:].isdigit():
        return "Casier final"
    return "Zone parent" if location.parent_id else "Magasin"


def _purchase_location_quality_issues(db: Session, location: models.StockLocation | None) -> list[str]:
    if not location:
        return ["emplacement absent"]
    name = (location.name or "").strip().lower()
    first_word = name.split(" ", 1)[0] if name else ""
    compact_slot = len(name) >= 2 and name[0].isalpha() and name[1:].isdigit()
    role = _purchase_location_role(db, location)
    issues = []
    if not name:
        issues.append("nom absent")
    if name and len(name) < 3 and not compact_slot:
        issues.append("nom trop court")
    if name in _VAGUE_LOCATION_WORDS or first_word in (_VAGUE_LOCATION_WORDS - {"zone"}):
        issues.append("nom trop vague")
    if role in {"Magasin", "Zone parent"}:
        issues.append("rack, casier ou zone atelier à préciser")
    return issues


def _is_purchase_exploitable_location(db: Session, location: models.StockLocation | None) -> bool:
    return bool(
        location
        and location.is_active
        and location.usage == "internal"
        and not _purchase_location_quality_issues(db, location)
    )


def _purchase_stock_quantities_by_location_quality(db: Session, variant_id: int) -> dict[str, Any]:
    rows = (
        db.query(models.StockQuant)
        .join(models.StockLocation, models.StockQuant.location_id == models.StockLocation.id)
        .filter(
            models.StockQuant.variant_id == variant_id,
            models.StockLocation.usage == "internal",
            models.StockLocation.is_active == True,
        )
        .all()
    )
    exploitable = 0.0
    unclear = 0.0
    unclear_locations = []
    for quant in rows:
        quantity = float(quant.quantity or 0)
        if quantity == 0:
            continue
        location = quant.location
        if _is_purchase_exploitable_location(db, location):
            exploitable += quantity
        else:
            unclear += quantity
            if location:
                unclear_locations.append({
                    "location_id": location.id,
                    "location_name": _purchase_location_full_name(db, location),
                    "quantity": quantity,
                    "issues": _purchase_location_quality_issues(db, location),
                })
    return {
        "physical_quantity": exploitable + unclear,
        "exploitable_quantity": exploitable,
        "unclear_quantity": unclear,
        "unclear_locations": unclear_locations[:5],
    }


def _purchase_supplier_map(db: Session) -> dict[str, models.Supplier]:
    return {
        supplier.name.upper(): supplier
        for supplier in db.query(models.Supplier).all()
        if supplier.name
    }


def _open_purchase_remaining_by_variant(db: Session) -> dict[int, float]:
    rows = (
        db.query(models.PurchaseOrderLine)
        .join(models.PurchaseOrder, models.PurchaseOrderLine.order_id == models.PurchaseOrder.id)
        .filter(models.PurchaseOrder.status != models.PurchaseOrderStatus.CANCELLED)
        .all()
    )
    incoming: dict[int, float] = {}
    for line in rows:
        remaining = max(float(line.quantity or 0) - float(line.quantity_received or 0), 0.0)
        if remaining > 0:
            incoming[line.variant_id] = incoming.get(line.variant_id, 0.0) + remaining
    return incoming


def _open_purchase_request_quantity_by_variant(db: Session) -> dict[int, float]:
    rows = (
        db.query(models.PurchaseRequestLine)
        .join(models.PurchaseRequest, models.PurchaseRequestLine.request_id == models.PurchaseRequest.id)
        .filter(models.PurchaseRequest.status.in_([
            models.PurchaseRequestStatus.PENDING_APPROVAL,
            models.PurchaseRequestStatus.APPROVED,
        ]))
        .all()
    )
    requested: dict[int, float] = {}
    for line in rows:
        quantity = max(float(line.quantity or 0), 0.0)
        if quantity > 0:
            requested[line.variant_id] = requested.get(line.variant_id, 0.0) + quantity
    return requested


def _procurement_target_quantity(min_threshold: float, supplier_lead_time_days: int | None = None) -> float:
    if min_threshold <= 0:
        return 1.0
    coverage_factor = 2.0
    if supplier_lead_time_days and supplier_lead_time_days >= 30:
        coverage_factor = 3.0
    elif supplier_lead_time_days and supplier_lead_time_days >= 14:
        coverage_factor = 2.5
    return min_threshold * coverage_factor


def _near_threshold_multiplier(supplier_lead_time_days: int | None = None) -> float:
    if supplier_lead_time_days and supplier_lead_time_days >= 30:
        return 1.75
    if supplier_lead_time_days and supplier_lead_time_days >= 14:
        return 1.5
    return 1.25


def _purchase_need_priority(
    available_quantity: float,
    min_threshold: float,
    net_need_quantity: float,
    *,
    requires_location_clarification: bool = False,
) -> str:
    if net_need_quantity <= 0 and requires_location_clarification:
        return "TO_PLAN"
    if net_need_quantity <= 0:
        return "COVERED"
    if available_quantity <= 0:
        return "CRITICAL"
    if min_threshold > 0 and available_quantity < min_threshold:
        return "URGENT"
    return "TO_PLAN"


def _purchase_need_profile(db: Session) -> dict[str, Any]:
    suppliers = _purchase_supplier_map(db)
    incoming_by_variant = _open_purchase_remaining_by_variant(db)
    open_requests_by_variant = _open_purchase_request_quantity_by_variant(db)
    rows = (
        db.query(models.ProductVariant)
        .join(models.Product, models.Product.id == models.ProductVariant.product_id)
        .filter(
            models.Product.product_type != "service",
            models.Product.catalog_status == "ACTIVE",
        )
        .all()
    )
    status_counts = {
        "CRITICAL": 0,
        "URGENT": 0,
        "TO_PLAN": 0,
        "BLOCKED": 0,
        "COVERED": 0,
    }
    signal_counts = {
        "UNCLEAR_STOCK_LOCATION": 0,
        "OPEN_PURCHASE_ORDER": 0,
        "OPEN_PURCHASE_REQUEST": 0,
        "LONG_SUPPLIER_LEAD_TIME": 0,
        "SUPPLIER_MISSING": 0,
        "SUPPLIER_BLOCKED": 0,
    }
    record_count = 0
    orderable_count = 0
    blocked_count = 0
    net_need_quantity_total = 0.0
    suggested_quantity_total = 0.0
    supplier_names: set[str] = set()
    top_blockers: list[dict[str, Any]] = []

    for variant in rows:
        product = variant.product
        if not product:
            continue
        threshold = float(variant.min_threshold or 0)
        stock_quality = _purchase_stock_quantities_by_location_quality(db, variant.id)
        physical_quantity = float(stock_quality["physical_quantity"])
        exploitable_quantity = float(stock_quality["exploitable_quantity"])
        unclear_quantity = float(stock_quality["unclear_quantity"])
        reserved_quantity = active_reserved_quantity(db, variant.id)
        available_quantity = max(exploitable_quantity - reserved_quantity, 0.0)
        total_available_quantity = max(physical_quantity - reserved_quantity, 0.0)
        incoming_purchase_quantity = float(incoming_by_variant.get(variant.id, 0.0))
        open_request_quantity = float(open_requests_by_variant.get(variant.id, 0.0))
        supplier_name = (product.supplier or "").strip()
        supplier = suppliers.get(supplier_name.upper()) if supplier_name else None
        supplier_lead_time_days = supplier.lead_time_days if supplier else None

        target_quantity = _procurement_target_quantity(threshold, supplier_lead_time_days)
        is_near_threshold = threshold > 0 and available_quantity <= threshold * _near_threshold_multiplier(supplier_lead_time_days)
        gross_need_quantity = max(target_quantity - available_quantity, 0.0)
        gross_need_after_unclear_stock = max(target_quantity - total_available_quantity, 0.0)
        requires_location_clarification = unclear_quantity > 0 and gross_need_quantity > gross_need_after_unclear_stock
        if available_quantity > 0 and not is_near_threshold and not requires_location_clarification:
            continue
        if threshold <= 0 and available_quantity > 0 and not requires_location_clarification:
            continue

        net_need_quantity = max(gross_need_after_unclear_stock - incoming_purchase_quantity - open_request_quantity, 0.0)
        supplier_status = supplier.supplier_status if supplier else None
        is_supplier_blocked = supplier_status == "BLOCKED" or bool(supplier and not supplier.is_active)
        is_orderable = (
            bool(supplier_name)
            and supplier is not None
            and not is_supplier_blocked
            and net_need_quantity > 0
            and not requires_location_clarification
        )
        priority = _purchase_need_priority(
            available_quantity,
            threshold,
            net_need_quantity,
            requires_location_clarification=requires_location_clarification,
        )

        record_count += 1
        if supplier_name:
            supplier_names.add(supplier_name)
        computed_status = priority
        if not supplier_name or supplier is None:
            signal_counts["SUPPLIER_MISSING"] += 1
            blocked_count += 1
            computed_status = "BLOCKED"
        elif is_supplier_blocked:
            signal_counts["SUPPLIER_BLOCKED"] += 1
            blocked_count += 1
            computed_status = "BLOCKED"
        elif requires_location_clarification:
            blocked_count += 1
            computed_status = "BLOCKED"
        status_counts[computed_status] = status_counts.get(computed_status, 0) + 1
        if requires_location_clarification:
            signal_counts["UNCLEAR_STOCK_LOCATION"] += 1
        if incoming_purchase_quantity > 0:
            signal_counts["OPEN_PURCHASE_ORDER"] += 1
        if open_request_quantity > 0:
            signal_counts["OPEN_PURCHASE_REQUEST"] += 1
        if supplier_lead_time_days and supplier_lead_time_days >= 14:
            signal_counts["LONG_SUPPLIER_LEAD_TIME"] += 1
        if is_orderable:
            orderable_count += 1

        suggested_quantity = max(
            target_quantity - total_available_quantity - incoming_purchase_quantity - open_request_quantity,
            0.0,
        )
        package_size = float(variant.units_per_package or 0)
        if suggested_quantity > 0 and package_size > 1:
            suggested_quantity = ((suggested_quantity + package_size - 1) // package_size) * package_size
        net_need_quantity_total += net_need_quantity
        suggested_quantity_total += suggested_quantity

        if len(top_blockers) < 8 and not is_orderable and priority != "COVERED":
            if not supplier_name:
                blocker = "SUPPLIER_MISSING"
            elif supplier is None:
                blocker = "SUPPLIER_NOT_IN_REFERENTIAL"
            elif is_supplier_blocked:
                blocker = "SUPPLIER_BLOCKED"
            elif requires_location_clarification:
                blocker = "UNCLEAR_STOCK_LOCATION"
            else:
                blocker = "REFERENCE_TO_QUALIFY"
            top_blockers.append({
                "variant_id": variant.id,
                "product_id": product.id,
                "reference": variant.reference,
                "product_name": product.name,
                "supplier": supplier_name or None,
                "blocker": blocker,
                "priority": priority,
                "net_need_quantity": net_need_quantity,
            })

    return {
        "record_count": record_count,
        "status_field": "computed_need_status",
        "status_counts": {key: value for key, value in status_counts.items() if value},
        "signal_counts": {key: value for key, value in signal_counts.items() if value},
        "orderable_count": orderable_count,
        "blocked_count": blocked_count,
        "supplier_count": len(supplier_names),
        "net_need_quantity_total": net_need_quantity_total,
        "suggested_quantity_total": suggested_quantity_total,
        "top_blockers": top_blockers,
        "calculation": (
            "Stock exploitable par emplacement, réservations actives, seuil, délai fournisseur, "
            "commandes/demandes ouvertes et qualification fournisseur."
        ),
    }


def _external_document_profile(db: Session) -> dict[str, Any]:
    rows = (
        db.query(
            models.TechnicalDossierVersion.source_system,
            models.TechnicalDossierVersion.document_type,
            func.count(models.TechnicalDossierVersion.id),
        )
        .group_by(
            models.TechnicalDossierVersion.source_system,
            models.TechnicalDossierVersion.document_type,
        )
        .all()
    )
    observed = []
    for source_system, document_type, count in rows:
        mapping = resolve_external_document(source_system or "", document_type or "")
        document_meta = DOCUMENT_TYPES.get(str(document_type or "").upper(), {})
        observed.append(
            {
                "source_system": source_system,
                "document_type": document_type,
                "record_count": int(count or 0),
                "canonical_entity": mapping.canonical_entity if mapping else None,
                "canonical_label": mapping.label if mapping else None,
                "stock_source": bool(document_meta.get("stock_source", False)),
            }
        )
    return {
        "record_count": _scalar_count(db, models.TechnicalDossierVersion),
        "by_source_system": _group_counts(
            db,
            models.TechnicalDossierVersion,
            models.TechnicalDossierVersion.source_system,
        ),
        "by_document_type": _group_counts(
            db,
            models.TechnicalDossierVersion,
            models.TechnicalDossierVersion.document_type,
        ),
        "observed_mappings": observed,
    }


def _rbac_profile(db: Session) -> dict[str, Any]:
    declared_codes = sorted({permission.permission for permission in STEP_RBAC})
    available_permissions = {
        permission.code: permission
        for permission in (
            db.query(models.Permission)
            .filter(models.Permission.code.in_(declared_codes))
            .all()
        )
    }
    role_rows = (
        db.query(models.Permission.code, models.Role.name)
        .join(models.RolePermission, models.RolePermission.permission_id == models.Permission.id)
        .join(models.Role, models.Role.id == models.RolePermission.role_id)
        .filter(models.Permission.code.in_(declared_codes))
        .order_by(models.Permission.code.asc(), models.Role.name.asc())
        .all()
    )
    roles_by_permission: dict[str, list[str]] = {code: [] for code in declared_codes}
    for code, role_name in role_rows:
        roles_by_permission.setdefault(code, []).append(role_name)
    return {
        "declared_step_permissions": declared_codes,
        "available_permissions": {
            code: code in available_permissions for code in declared_codes
        },
        "missing_permissions": [
            code for code in declared_codes if code not in available_permissions
        ],
        "roles_by_permission": roles_by_permission,
    }


def ontology_with_data_profile(db: Session) -> dict[str, Any]:
    payload = ontology_as_dict()
    payload["data_profile"] = {
        "generated_at": utcnow().isoformat(),
        "entities": {
            "client": _entity_profile(db, models.Client),
            "contact": _entity_profile(db, models.ClientContact),
            "crm_opportunity": _entity_profile(
                db,
                models.CRMOpportunity,
                status_column=models.CRMOpportunity.stage,
            ),
            "measure_mission": _entity_profile(
                db,
                models.MeasureMission,
                status_column=models.MeasureMission.status,
            ),
            "technical_dossier": _entity_profile(
                db,
                models.TechnicalDossier,
                status_column=models.TechnicalDossier.production_status,
            ),
            "technical_quotation": _technical_version_profile(
                db,
                "technical_quotation",
                ("QUOTING", "VALUATION"),
            ),
            "commercial_quote": _entity_profile(
                db,
                models.SaleOrder,
                status_column=models.SaleOrder.status,
            ),
            "signed_order": _entity_profile(
                db,
                models.SaleOrder,
                status_column=models.SaleOrder.status,
                criteria=(models.SaleOrder.signed_at.isnot(None),),
            ),
            "industrial_dossier": _entity_profile(
                db,
                models.TechnicalDossier,
                status_column=models.TechnicalDossier.launch_status,
            ),
            "fabrication_sheet": _technical_version_profile(
                db,
                "fabrication_sheet",
                ("FABRICATION",),
            ),
            "cutting_sheet": _technical_version_profile(
                db,
                "cutting_sheet",
                ("CUTTING",),
            ),
            "stock_item": _entity_profile(db, models.ProductVariant),
            "stock_reservation": _entity_profile(
                db,
                models.StockReservation,
                status_column=models.StockReservation.status,
            ),
            "workshop_preparation": _entity_profile(
                db,
                models.WorkshopPreparation,
                status_column=models.WorkshopPreparation.status,
            ),
            "production_order": _entity_profile(db, models.Order),
            "real_workshop_debit": _entity_profile(
                db,
                models.StockMove,
                status_column=models.StockMove.state,
            ),
            "inventory_session": _entity_profile(
                db,
                models.InventorySession,
                status_column=models.InventorySession.status,
            ),
            "inventory_count_line": _entity_profile(
                db,
                models.InventoryCountLine,
                status_column=models.InventoryCountLine.status,
            ),
            "supplier": _entity_profile(
                db,
                models.Supplier,
                status_column=models.Supplier.supplier_status,
            ),
            "purchase_need": _purchase_need_profile(db),
            "purchase_request": _entity_profile(
                db,
                models.PurchaseRequest,
                status_column=models.PurchaseRequest.status,
            ),
            "purchase_order": _entity_profile(
                db,
                models.PurchaseOrder,
                status_column=models.PurchaseOrder.status,
            ),
            "purchase_receipt": _entity_profile(
                db,
                models.PurchaseOrderLine,
                criteria=(models.PurchaseOrderLine.quantity_received > 0,),
            ),
            "supplier_invoice": _entity_profile(
                db,
                models.SupplierInvoice,
                status_column=models.SupplierInvoice.status,
            ),
            "supplier_payment": _entity_profile(db, models.SupplierPayment),
            "supplier_dispute": _entity_profile(
                db,
                models.SupplierDispute,
                status_column=models.SupplierDispute.status,
            ),
        },
        "external_documents": _external_document_profile(db),
        "rbac": _rbac_profile(db),
    }
    return payload

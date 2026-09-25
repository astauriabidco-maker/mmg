from __future__ import annotations

from collections.abc import Iterable
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
        str(value if value is not None else "UNKNOWN"): int(count or 0)
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
        },
        "external_documents": _external_document_profile(db),
        "rbac": _rbac_profile(db),
    }
    return payload

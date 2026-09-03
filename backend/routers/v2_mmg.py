from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, File, Form, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from pathlib import Path
import os
import base64
import csv
import hashlib
import io
import uuid
from datetime import datetime, timedelta
from ..database import get_db
from .. import models, schemas
from ..core import security
from ..core import uploads
from ..core.events import _send_smtp_email, _smtp_settings
from ..domain.ontology import ontology_as_dict
from ..services.document_sequences import next_number
from ..services.technical_document_analysis import analyze_technical_document
from ..services.commercial_quote_analysis import compare_commercial_quote_versions
from ..services.crm_cockpit import build_crm_cockpit
from ..services.crm_reminders import (
    build_template_context,
    record_reminder_delivery,
    ensure_default_rules,
    ensure_default_templates,
    reminder_template_code,
    render_email,
    sync_reminder_plans,
)
from ..services.crm_opportunity_workflow import (
    set_opportunity_stage,
    sync_opportunity_from_mission,
    sync_opportunity_from_sale,
)
from ..services.technical_dossier_governance import (
    build_document_matrix,
    compare_material_versions,
)
from ..services.stock_reservations import (
    create_reservation,
    preview_records,
    reactivate_cancelled_reservation,
)
from ..core.time import utcnow
from scripts.import_workshop_debits import DebitRecord

router = APIRouter(
    prefix="/v2/mmg",
    tags=["mmg"],
    dependencies=[Depends(security.get_current_user)],
)
CRM_VIEW_DEPENDENCIES = [
    Depends(security.require_permissions("SALES_VIEW")),
]
CRM_EDIT_DEPENDENCIES = [
    Depends(security.require_permissions("SALES_EDIT")),
]


@router.get("/ontology")
def get_mmg_business_ontology():
    """Expose le référentiel métier MMG pour l'UI, les parseurs et les usages IA/RAG."""

    return ontology_as_dict()


# Helper to save base64 image
def save_base64_image(base64_str: str, folder: str, prefix: str):
    img_data, extension = uploads.decode_base64_upload(base64_str)
    filename = f"{prefix}_{uuid.uuid4().hex[:8]}{extension}"
    # /uploads est le seul montage statique de main.py (volume persistant en prod)
    filepath = os.path.join("uploads", "mmg", folder, filename)

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "wb") as f:
        f.write(img_data)

    return f"/uploads/mmg/{folder}/{filename}"


def _serialize_detail(db_item: models.MMG) -> schemas.MMGDetail:
    status = db_item.status.value if hasattr(db_item.status, "value") else db_item.status
    return schemas.MMGDetail(
        id=db_item.id,
        reference=db_item.reference,
        client_name=db_item.client_name,
        client_id=db_item.client_id,
        site_address_id=db_item.site_address_id,
        measure_mission_id=db_item.measure_mission_id,
        status=status,
        created_at=db_item.created_at,
        client_contact=db_item.client_contact,
        client_address=db_item.client_address,
        site_address=db_item.site_address,
        client_email=db_item.client_email,
        client_type=db_item.client_type,
        width=db_item.width,
        height=db_item.height,
        passage_height=db_item.passage_height,
        sill_height=db_item.sill_height,
        transom_height=db_item.transom_height,
        shutter_type=db_item.shutter_type,
        opening_type=db_item.opening_type,
        opening_side=db_item.opening_side,
        sash_count=db_item.sash_count,
        view_type=db_item.view_type,
        material=db_item.material,
        product_series=db_item.product_series,
        color_ral=db_item.color_ral,
        is_bicolor=db_item.is_bicolor,
        texture=db_item.texture,
        glazing_type=db_item.glazing_type,
        installation_type=db_item.installation_type,
        hardware_type=db_item.hardware_type,
        is_pmr_compliant=db_item.is_pmr_compliant,
        doublage_thickness=db_item.doublage_thickness,
        keep_existing_frame=db_item.keep_existing_frame,
        floor_number=db_item.floor_number or 0,
        access_difficulty=db_item.access_difficulty,
        environment=db_item.environment,
        quote_sent_at=db_item.quote_sent_at,
        photos=db_item.photos.split(",") if db_item.photos else [],
        signature=db_item.signature or "",
        sale_order_id=db_item.sale_order_id,
        order_id=db_item.order_id,
        configuration=db_item.configuration or None,
    )

def generate_reference(db: Session):
    # Format: MMG-YYYY-XXXXX — séquence transactionnelle (NF525)
    return next_number(db, "mmg")


def _site_address_text(site: models.ClientSiteAddress) -> str:
    return site.formatted_address


def _serialize_mission(mission: models.MeasureMission) -> schemas.MeasureMissionResponse:
    assigned_user_name = None
    if mission.assigned_user:
        full_name = " ".join(
            part for part in [mission.assigned_user.first_name, mission.assigned_user.last_name] if part
        )
        assigned_user_name = full_name or mission.assigned_user.username
    return schemas.MeasureMissionResponse(
        id=mission.id,
        reference=mission.reference,
        client_id=mission.client_id,
        client_name=mission.client.name,
        site_address_id=mission.site_address_id,
        site=mission.site,
        opportunity_id=mission.opportunity_id,
        sale_order_id=mission.sale_order_id,
        sale_order_status=mission.sale_order.status if mission.sale_order else None,
        assigned_user_id=mission.assigned_user_id,
        assigned_user_name=assigned_user_name,
        status=mission.status,
        source_type=mission.source_type,
        project_scope=mission.project_scope,
        verification_status=mission.verification_status,
        purpose=mission.purpose,
        scheduled_start=mission.scheduled_start,
        scheduled_end=mission.scheduled_end,
        notes=mission.notes,
        client_approved_at=mission.client_approved_at,
        client_approved_by=mission.client_approved_by,
        site_verified_at=mission.site_verified_at,
        site_verified_by=mission.site_verified_by,
        dossier_ids=[dossier.id for dossier in mission.dossiers],
        openings=mission.openings,
        source_documents=mission.source_documents,
        technical_dossier=mission.technical_dossier,
        created_by=mission.created_by,
        created_at=mission.created_at,
        updated_at=mission.updated_at,
    )


def _get_or_create_technical_dossier(
    db: Session,
    mission: models.MeasureMission,
    actor: str,
) -> models.TechnicalDossier:
    if mission.technical_dossier:
        return mission.technical_dossier
    dossier = models.TechnicalDossier(
        reference=next_number(db, "technical_dossier"),
        mission=mission,
        quoting_status=schemas.TechnicalDossierStatus.DRAFT.value,
        production_status=schemas.TechnicalDossierStatus.LOCKED.value,
        created_by=actor,
    )
    db.add(dossier)
    db.flush()
    return dossier


def _latest_technical_version(
    dossier: models.TechnicalDossier,
    document_type: Optional[str] = None,
) -> Optional[models.TechnicalDossierVersion]:
    versions = [
        version
        for version in dossier.versions
        if document_type is None or version.document_type == document_type
    ]
    return versions[-1] if versions else None


def _sale_is_signed(mission: models.MeasureMission) -> bool:
    return bool(
        mission.sale_order
        and mission.sale_order.status in {
            "VALIDATED",
            "IN_DESIGN",
            "READY_FOR_PROD",
            "IN_PRODUCTION",
            "DELIVERED",
        }
        and mission.sale_order.signed_at
    )


def _validate_technical_coverage(
    mission: models.MeasureMission,
    opening_ids: List[int],
) -> None:
    mission_opening_ids = {opening.id for opening in mission.openings}
    supplied_ids = set(opening_ids)
    unknown_ids = supplied_ids - mission_opening_ids
    if unknown_ids:
        raise HTTPException(
            422,
            f"Ouvrage(s) hors mission: {', '.join(str(value) for value in sorted(unknown_ids))}",
        )
    missing_ids = mission_opening_ids - supplied_ids
    if missing_ids:
        raise HTTPException(
            422,
            f"Le dossier technique ne couvre pas {len(missing_ids)} ouvrage(s) de la mission",
        )


def _validate_production_document_analysis(
    dossier: models.TechnicalDossier,
) -> models.TechnicalDossierVersion:
    fabrication = _latest_technical_version(
        dossier,
        schemas.TechnicalDocumentType.FABRICATION.value,
    )
    cutting = _latest_technical_version(
        dossier,
        schemas.TechnicalDocumentType.CUTTING.value,
    )
    if not fabrication or not cutting:
        raise HTTPException(422, "Ajoutez les fichiers fabrication et débit")
    if (
        cutting.analysis_status not in {"PARSED", "PARSED_WITH_WARNINGS"}
        or not cutting.parsed_records
    ):
        raise HTTPException(
            422,
            "Le fichier de débit n'est pas exploitable automatiquement. "
            "Importez un SEPVER.TXT ou un Débit optimisé ORGADATA reconnu.",
        )

    fabrication_reference = (
        fabrication.detected_project_reference or fabrication.source_reference
    )
    cutting_reference = cutting.detected_project_reference or cutting.source_reference
    if (
        fabrication_reference
        and cutting_reference
        and fabrication_reference != cutting_reference
    ):
        raise HTTPException(
            409,
            "La fiche de fabrication et le débit ne portent pas la même référence "
            f"({fabrication_reference} / {cutting_reference}).",
        )
    return cutting


def _validate_quoting_document_analysis(
    dossier: models.TechnicalDossier,
) -> models.TechnicalDossierVersion:
    quoting = _latest_technical_version(
        dossier,
        schemas.TechnicalDocumentType.QUOTING.value,
    )
    if not quoting:
        raise HTTPException(422, "Ajoutez le chiffrage PROGES ou ORGADATA")
    if (
        quoting.analysis_status not in {"PARSED", "PARSED_WITH_WARNINGS"}
        or not quoting.parsed_records
    ):
        raise HTTPException(
            422,
            "Le chiffrage n'est pas exploitable automatiquement. "
            "Importez un devis PDF PROGES ou ORGADATA reconnu.",
        )
    blocking_issues = [
        issue
        for issue in quoting.parsed_issues or []
        if issue.get("severity") == "error"
    ]
    if blocking_issues:
        raise HTTPException(
            422,
            "Le chiffrage contient des anomalies bloquantes : "
            + "; ".join(issue.get("message", "anomalie") for issue in blocking_issues[:3]),
        )
    if quoting.source_system not in {
        schemas.TechnicalSourceSystem.PROGES.value,
        schemas.TechnicalSourceSystem.ORGADATA.value,
    }:
        raise HTTPException(422, "Le chiffrage doit provenir de PROGES ou ORGADATA")
    summary = quoting.parsed_summary or {}
    if float(summary.get("subtotal_after_discount") or 0) <= 0:
        raise HTTPException(422, "Le total HT net du chiffrage doit être positif")
    return quoting


def _records_from_technical_version(
    version: models.TechnicalDossierVersion,
) -> list[DebitRecord]:
    records = []
    for record in version.parsed_records or []:
        records.append(
            DebitRecord(
                source=str(record.get("source") or version.original_filename),
                row=record.get("row"),
                supplier=str(record.get("supplier") or ""),
                reference=str(record.get("reference") or ""),
                designation=str(
                    record.get("designation") or record.get("reference") or ""
                ),
                quantity=float(record.get("quantity") or 0),
                unit=str(record.get("unit") or "unité"),
                project_reference=record.get("project_reference"),
                color=record.get("color"),
                length_mm=record.get("length_mm"),
                position=record.get("position"),
                cut_left_deg=record.get("cut_left_deg"),
                cut_right_deg=record.get("cut_right_deg"),
                cut_orientation=record.get("cut_orientation"),
            )
        )
    return records


def _material_signature_from_records(records: list[DebitRecord]) -> dict[tuple[str, str, str], float]:
    signature: dict[tuple[str, str, str], float] = {}
    for record in records:
        key = (
            (record.supplier or "").strip().upper(),
            (record.reference or "").strip().upper(),
            (record.unit or "").strip().lower(),
        )
        signature[key] = signature.get(key, 0.0) + float(record.quantity or 0)
    return signature


def _material_signature_from_reservation(
    reservation: models.StockReservation,
) -> dict[tuple[str, str, str], float]:
    signature: dict[tuple[str, str, str], float] = {}
    for line in reservation.lines or []:
        key = (
            (line.supplier or "").strip().upper(),
            (line.supplier_reference or "").strip().upper(),
            (line.unit or "").strip().lower(),
        )
        quantity = float(line.consumed_quantity or line.reserved_quantity or 0)
        signature[key] = signature.get(key, 0.0) + quantity
    return signature


def _consumed_reservation_matches_cutting(
    reservation: Optional[models.StockReservation],
    cutting: models.TechnicalDossierVersion,
) -> bool:
    if not reservation or reservation.status != "consumed":
        return False
    return _material_signature_from_reservation(reservation) == _material_signature_from_records(
        _records_from_technical_version(cutting)
    )


def _technical_stock_snapshot(
    db: Session,
    dossier: models.TechnicalDossier,
) -> dict:
    cutting = _latest_technical_version(
        dossier,
        schemas.TechnicalDocumentType.CUTTING.value,
    )
    if not cutting or not cutting.parsed_records:
        return {
            "ready": False,
            "line_count": 0,
            "ok_count": 0,
            "unknown_count": 0,
            "shortage_count": 0,
            "matches": [],
        }
    matches = preview_records(
        db,
        _records_from_technical_version(cutting),
        "WH/Stock",
    )
    return {
        "ready": bool(matches) and all(match.status == "ok" for match in matches),
        "line_count": len(matches),
        "ok_count": sum(match.status == "ok" for match in matches),
        "unknown_count": sum(match.status == "not_found" for match in matches),
        "shortage_count": sum(match.status == "shortage" for match in matches),
        "matches": [match.__dict__ for match in matches],
    }


def _technical_execution_context(
    db: Session,
    mission: models.MeasureMission,
) -> dict:
    reservation = None
    preparation = None
    production_orders = []
    if mission.sale_order_id:
        reservation = (
            db.query(models.StockReservation)
            .filter(
                models.StockReservation.sale_order_id == mission.sale_order_id,
                models.StockReservation.source_label.notin_(["devis libre", "devis_libre"]),
            )
            .order_by(models.StockReservation.created_at.desc())
            .first()
        )
        if reservation:
            preparation = (
                db.query(models.WorkshopPreparation)
                .filter(models.WorkshopPreparation.reservation_id == reservation.id)
                .first()
            )
        production_orders = (
            db.query(models.Order)
            .filter(models.Order.sale_order_id == mission.sale_order_id)
            .order_by(models.Order.id)
            .all()
        )
    return {
        "sale_order_id": mission.sale_order_id,
        "reservation": {
            "id": reservation.id,
            "reference": reservation.reference,
            "status": reservation.status,
            "source_label": reservation.source_label,
            "technical_dossier_version_id": reservation.technical_dossier_version_id,
        } if reservation else None,
        "preparation": {
            "id": preparation.id,
            "reference": preparation.reference,
            "status": preparation.status,
        } if preparation else None,
        "production_orders": [
            {"id": order.id, "reference": order.reference}
            for order in production_orders
        ],
    }


def _technical_governance_payload(
    db: Session,
    mission: models.MeasureMission,
) -> dict:
    dossier = mission.technical_dossier
    if not dossier:
        raise HTTPException(404, "Dossier technique introuvable")
    latest_cutting = _latest_technical_version(
        dossier,
        schemas.TechnicalDocumentType.CUTTING.value,
    )
    execution = _technical_execution_context(db, mission)
    if execution["reservation"] and latest_cutting:
        execution["reservation"]["cutting_version_id"] = (
            latest_cutting.id
            if execution["reservation"]["technical_dossier_version_id"]
            == latest_cutting.id
            else None
        )
    return {
        "dossier_reference": dossier.reference,
        "external_source_system": dossier.external_source_system,
        "external_project_reference": dossier.external_project_reference,
        "document_matrix": build_document_matrix(dossier.versions),
        "stock": _technical_stock_snapshot(db, dossier),
        "execution": execution,
        "gates": {
            "be": dossier.production_status,
            "stock": dossier.stock_status,
            "launch": dossier.launch_status,
        },
        "latest_revision": {
            "version_id": latest_cutting.id,
            "version_number": latest_cutting.version_number,
            "impact_status": latest_cutting.impact_status,
            "revision_after_launch": latest_cutting.revision_after_launch,
            "revision_status": latest_cutting.revision_status,
            "comparison_summary": latest_cutting.comparison_summary or {},
        } if latest_cutting else None,
    }


def _resolve_site(
    db: Session,
    client_id: int,
    site_address_id: Optional[int] = None,
    site_data: Optional[schemas.ClientSiteAddressCreate] = None,
) -> Optional[models.ClientSiteAddress]:
    if site_address_id:
        site = db.query(models.ClientSiteAddress).filter(models.ClientSiteAddress.id == site_address_id).first()
        if not site:
            raise HTTPException(404, "Adresse chantier introuvable")
        if site.client_id != client_id:
            raise HTTPException(400, "Cette adresse chantier n'appartient pas au client sélectionné")
        return site

    if not site_data:
        return None

    normalized_line1 = site_data.address_line1.strip()
    existing = (
        db.query(models.ClientSiteAddress)
        .filter(
            models.ClientSiteAddress.client_id == client_id,
            func.lower(models.ClientSiteAddress.address_line1) == normalized_line1.lower(),
            func.lower(func.coalesce(models.ClientSiteAddress.postal_code, ""))
            == (site_data.postal_code or "").strip().lower(),
            func.lower(func.coalesce(models.ClientSiteAddress.city, ""))
            == (site_data.city or "").strip().lower(),
        )
        .first()
    )
    if existing:
        return existing

    if site_data.is_default:
        db.query(models.ClientSiteAddress).filter(
            models.ClientSiteAddress.client_id == client_id
        ).update({"is_default": False}, synchronize_session=False)

    payload = site_data.model_dump(exclude={"client_id"})
    payload["address_line1"] = normalized_line1
    site = models.ClientSiteAddress(
        reference=next_number(db, "client_site"),
        client_id=client_id,
        **payload,
    )
    db.add(site)
    db.flush()
    return site


MISSION_TRANSITIONS = {
    models.MeasureMissionStatus.DRAFT.value: {
        models.MeasureMissionStatus.TO_SCHEDULE.value,
        models.MeasureMissionStatus.SCHEDULED.value,
        models.MeasureMissionStatus.IN_CAPTURE.value,
        models.MeasureMissionStatus.CANCELLED.value,
    },
    models.MeasureMissionStatus.TO_SCHEDULE.value: {
        models.MeasureMissionStatus.SCHEDULED.value,
        models.MeasureMissionStatus.CANCELLED.value,
    },
    models.MeasureMissionStatus.SCHEDULED.value: {
        models.MeasureMissionStatus.IN_CAPTURE.value,
        models.MeasureMissionStatus.ON_SITE.value,
        models.MeasureMissionStatus.CANCELLED.value,
    },
    models.MeasureMissionStatus.IN_CAPTURE.value: {
        models.MeasureMissionStatus.TO_REVIEW.value,
        models.MeasureMissionStatus.SCHEDULED.value,
        models.MeasureMissionStatus.CANCELLED.value,
    },
    models.MeasureMissionStatus.ON_SITE.value: {
        models.MeasureMissionStatus.TO_REVIEW.value,
        models.MeasureMissionStatus.SCHEDULED.value,
    },
    models.MeasureMissionStatus.TO_REVIEW.value: {
        models.MeasureMissionStatus.CORRECTION_REQUIRED.value,
        models.MeasureMissionStatus.VALIDATED.value,
    },
    models.MeasureMissionStatus.CORRECTION_REQUIRED.value: {
        models.MeasureMissionStatus.IN_CAPTURE.value,
        models.MeasureMissionStatus.ON_SITE.value,
        models.MeasureMissionStatus.TO_REVIEW.value,
    },
    models.MeasureMissionStatus.VALIDATED.value: {
        models.MeasureMissionStatus.QUOTED.value,
    },
    models.MeasureMissionStatus.QUOTED.value: set(),
    models.MeasureMissionStatus.CANCELLED.value: set(),
}

MISSION_TERMINAL_STATUSES = {
    models.MeasureMissionStatus.QUOTED.value,
    models.MeasureMissionStatus.CANCELLED.value,
}

BE_REVIEW_ROLES = {
    "ADMIN",
    "MANAGER",
    "QUALITY_CONTROLLER",
    "WORKSHOP_LEAD",
    "TECHNICO_COMMERCIAL",
}
STOCK_REVIEW_ROLES = {"ADMIN", "MANAGER", "CHEF_STOCK"}
LAUNCH_REVIEW_ROLES = {"ADMIN", "MANAGER", "WORKSHOP_LEAD"}


def _assert_technical_edit(db: Session, current_user: dict) -> None:
    """Autorise l'édition au commerce ou aux rôles chargés du contrôle BE."""
    try:
        security.assert_permission(db, current_user, "SALES_EDIT")
        return
    except HTTPException as exc:
        if exc.status_code != 403:
            raise
    if _current_roles(current_user) & BE_REVIEW_ROLES:
        return
    raise HTTPException(403, "Permission SALES_EDIT ou rôle BE requis")


def _get_mission_or_404(db: Session, mission_id: int) -> models.MeasureMission:
    mission = db.query(models.MeasureMission).filter(models.MeasureMission.id == mission_id).first()
    if not mission:
        raise HTTPException(404, "Mission de métré introuvable")
    return mission


def _validate_opening_dimensions(opening) -> None:
    if opening.status in {
        schemas.MeasureOpeningStatus.COMPLETE.value,
        schemas.MeasureOpeningStatus.TO_REVIEW.value,
        schemas.MeasureOpeningStatus.VALIDATED.value,
    } and (not opening.width_mm or opening.width_mm <= 0 or not opening.height_mm or opening.height_mm <= 0):
        raise HTTPException(
            422,
            "Largeur et hauteur positives obligatoires pour terminer un ouvrage",
        )


def _ensure_mission_editable(mission: models.MeasureMission) -> None:
    if mission.status in MISSION_TERMINAL_STATUSES:
        raise HTTPException(409, "Cette mission est clôturée et ne peut plus être modifiée")


def _current_roles(current_user: dict) -> set[str]:
    roles = set(current_user.get("roles") or [])
    if current_user.get("role"):
        roles.add(current_user["role"])
    return roles


OPPORTUNITY_TRANSITIONS = {
    models.CRMOpportunityStage.NEW.value: {
        models.CRMOpportunityStage.QUALIFIED.value,
        models.CRMOpportunityStage.LOST.value,
    },
    models.CRMOpportunityStage.QUALIFIED.value: {
        models.CRMOpportunityStage.MEASURE_TO_SCHEDULE.value,
        models.CRMOpportunityStage.PROPOSAL_TO_PREPARE.value,
        models.CRMOpportunityStage.LOST.value,
    },
    models.CRMOpportunityStage.MEASURE_TO_SCHEDULE.value: {
        models.CRMOpportunityStage.MEASURE_IN_PROGRESS.value,
        models.CRMOpportunityStage.PROPOSAL_TO_PREPARE.value,
        models.CRMOpportunityStage.LOST.value,
    },
    models.CRMOpportunityStage.MEASURE_IN_PROGRESS.value: {
        models.CRMOpportunityStage.PROPOSAL_TO_PREPARE.value,
        models.CRMOpportunityStage.LOST.value,
    },
    models.CRMOpportunityStage.PROPOSAL_TO_PREPARE.value: {
        models.CRMOpportunityStage.PROPOSAL_TO_VALIDATE.value,
        models.CRMOpportunityStage.LOST.value,
    },
    models.CRMOpportunityStage.PROPOSAL_TO_VALIDATE.value: {
        models.CRMOpportunityStage.PROPOSAL_TO_PREPARE.value,
        models.CRMOpportunityStage.PROPOSAL_SENT.value,
        models.CRMOpportunityStage.LOST.value,
    },
    models.CRMOpportunityStage.PROPOSAL_SENT.value: {
        models.CRMOpportunityStage.NEGOTIATION.value,
        models.CRMOpportunityStage.WON.value,
        models.CRMOpportunityStage.LOST.value,
    },
    models.CRMOpportunityStage.NEGOTIATION.value: {
        models.CRMOpportunityStage.PROPOSAL_SENT.value,
        models.CRMOpportunityStage.WON.value,
        models.CRMOpportunityStage.LOST.value,
    },
    models.CRMOpportunityStage.LOST.value: {
        models.CRMOpportunityStage.QUALIFIED.value,
    },
    models.CRMOpportunityStage.WON.value: set(),
}

OPPORTUNITY_DERIVED_STAGES = {
    models.CRMOpportunityStage.QUALIFIED.value,
    models.CRMOpportunityStage.MEASURE_TO_SCHEDULE.value,
    models.CRMOpportunityStage.MEASURE_IN_PROGRESS.value,
    models.CRMOpportunityStage.PROPOSAL_TO_PREPARE.value,
    models.CRMOpportunityStage.PROPOSAL_TO_VALIDATE.value,
    models.CRMOpportunityStage.PROPOSAL_SENT.value,
    models.CRMOpportunityStage.WON.value,
}

ACTIVITY_TRANSITIONS = {
    models.CRMActivityStatus.TODO.value: {
        models.CRMActivityStatus.COMPLETED.value,
        models.CRMActivityStatus.CANCELLED.value,
    },
    models.CRMActivityStatus.COMPLETED.value: set(),
    models.CRMActivityStatus.CANCELLED.value: set(),
}


def _get_opportunity_or_404(db: Session, opportunity_id: int) -> models.CRMOpportunity:
    opportunity = (
        db.query(models.CRMOpportunity)
        .filter(models.CRMOpportunity.id == opportunity_id)
        .first()
    )
    if not opportunity:
        raise HTTPException(404, "Opportunité introuvable")
    return opportunity


def _get_activity_or_404(db: Session, activity_id: int) -> models.CRMActivity:
    activity = (
        db.query(models.CRMActivity)
        .filter(models.CRMActivity.id == activity_id)
        .first()
    )
    if not activity:
        raise HTTPException(404, "Activité CRM introuvable")
    return activity


def _validate_opportunity_links(
    db: Session,
    client_id: int,
    site_address_id: Optional[int] = None,
    owner_user_id: Optional[int] = None,
    sale_order_id: Optional[int] = None,
) -> None:
    if not db.query(models.Client).filter(models.Client.id == client_id).first():
        raise HTTPException(404, "Client introuvable")
    if site_address_id is not None:
        site = (
            db.query(models.ClientSiteAddress)
            .filter(models.ClientSiteAddress.id == site_address_id)
            .first()
        )
        if not site:
            raise HTTPException(404, "Adresse chantier introuvable")
        if site.client_id != client_id:
            raise HTTPException(400, "Le chantier et l'opportunité doivent appartenir au même client")
    if owner_user_id is not None:
        owner = (
            db.query(models.User)
            .filter(models.User.id == owner_user_id, models.User.is_active.is_(True))
            .first()
        )
        if not owner:
            raise HTTPException(400, "Responsable introuvable ou inactif")
    if sale_order_id is not None:
        if not db.query(models.SaleOrder).filter(models.SaleOrder.id == sale_order_id).first():
            raise HTTPException(404, "Devis converti introuvable")


def _validate_activity_links(
    db: Session,
    client_id: int,
    opportunity_id: Optional[int],
) -> Optional[models.CRMOpportunity]:
    if not db.query(models.Client).filter(models.Client.id == client_id).first():
        raise HTTPException(404, "Client introuvable")
    if opportunity_id is None:
        return None
    opportunity = _get_opportunity_or_404(db, opportunity_id)
    if opportunity.client_id != client_id:
        raise HTTPException(400, "L'activité et l'opportunité doivent appartenir au même client")
    return opportunity


@router.get(
    "/crm/cockpit",
    response_model=schemas.CRMCockpitResponse,
    dependencies=CRM_VIEW_DEPENDENCIES,
)
def get_crm_cockpit(
    owner_user_id: Optional[int] = None,
    horizon_days: int = 14,
    stale_days: int = 7,
    db: Session = Depends(get_db),
):
    if not 1 <= horizon_days <= 60:
        raise HTTPException(422, "L'horizon CRM doit être compris entre 1 et 60 jours")
    if not 1 <= stale_days <= 30:
        raise HTTPException(422, "Le délai d'inactivité doit être compris entre 1 et 30 jours")

    opportunities_query = db.query(models.CRMOpportunity)
    missions_query = db.query(models.MeasureMission)
    if owner_user_id is not None:
        owner = (
            db.query(models.User)
            .filter(models.User.id == owner_user_id, models.User.is_active.is_(True))
            .first()
        )
        if not owner:
            raise HTTPException(404, "Commercial ou métreur introuvable")
        opportunities_query = opportunities_query.filter(
            models.CRMOpportunity.owner_user_id == owner_user_id
        )
        missions_query = missions_query.filter(
            models.MeasureMission.assigned_user_id == owner_user_id
        )

    opportunities = opportunities_query.all()
    opportunity_ids = [item.id for item in opportunities]
    activities_query = db.query(models.CRMActivity)
    reminder_plans_query = db.query(models.CRMReminderPlan)
    stage_history_query = db.query(models.CRMOpportunityStageHistory)
    if owner_user_id is not None:
        activities_query = activities_query.filter(
            models.CRMActivity.opportunity_id.in_(opportunity_ids)
            if opportunity_ids
            else models.CRMActivity.id == -1
        )
        reminder_plans_query = reminder_plans_query.filter(
            models.CRMReminderPlan.assigned_user_id == owner_user_id
        )
        stage_history_query = stage_history_query.filter(
            models.CRMOpportunityStageHistory.opportunity_id.in_(opportunity_ids)
            if opportunity_ids
            else models.CRMOpportunityStageHistory.id == -1
        )

    return build_crm_cockpit(
        opportunities,
        activities_query.all(),
        missions_query.all(),
        reminder_plans=reminder_plans_query.all(),
        stage_history=stage_history_query.all(),
        sale_orders=db.query(models.SaleOrder).options(selectinload(models.SaleOrder.lines)).all(),
        now=utcnow(),
        horizon_days=horizon_days,
        stale_days=stale_days,
    )


@router.get(
    "/crm/cockpit/export.csv",
    dependencies=CRM_VIEW_DEPENDENCIES,
)
def export_crm_cockpit_csv(
    owner_user_id: Optional[int] = None,
    horizon_days: int = 14,
    stale_days: int = 7,
    db: Session = Depends(get_db),
):
    data = get_crm_cockpit(
        owner_user_id=owner_user_id,
        horizon_days=horizon_days,
        stale_days=stale_days,
        db=db,
    )
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "owner_name",
            "open_opportunities",
            "pipeline_amount",
            "weighted_pipeline_amount",
            "quotes_sent",
            "quotes_signed",
            "signed_amount",
            "conversion_rate",
            "reminders_today",
            "overdue_reminders",
            "opportunities_without_action",
            "attention_score",
        ],
    )
    writer.writeheader()
    for owner in data["owners"]:
        writer.writerow(owner)
    content = "\ufeff" + output.getvalue()
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="crm-pilotage-commercial.csv"'},
    )


def _crm_reminder_context(
    db: Session,
    client_id: int,
    opportunity_id: Optional[int],
):
    client = (
        db.query(models.Client)
        .options(selectinload(models.Client.contacts))
        .filter(models.Client.id == client_id)
        .first()
    )
    if not client:
        raise HTTPException(404, "Client introuvable")
    opportunity = None
    if opportunity_id is not None:
        opportunity = _get_opportunity_or_404(db, opportunity_id)
        if opportunity.client_id != client_id:
            raise HTTPException(409, "L'opportunité n'appartient pas à ce client")
    return client, opportunity


def _crm_reminder_template(
    db: Session,
    template_id: Optional[int],
    reminder_kind: Optional[str],
):
    ensure_default_templates(db)
    query = db.query(models.CRMReminderTemplate).filter(
        models.CRMReminderTemplate.is_active.is_(True)
    )
    if template_id is not None:
        template = query.filter(models.CRMReminderTemplate.id == template_id).first()
    else:
        template = query.filter(
            models.CRMReminderTemplate.code == reminder_template_code(reminder_kind)
        ).first()
    if not template:
        raise HTTPException(404, "Modèle de relance actif introuvable")
    return template


def _serialize_crm_delivery(delivery, notification=None):
    return {
        "id": delivery.id,
        "reminder_key": delivery.reminder_key,
        "client_id": delivery.client_id,
        "client_name": delivery.client_name,
        "opportunity_id": delivery.opportunity_id,
        "opportunity_reference": delivery.opportunity_reference,
        "template_id": delivery.template_id,
        "template_name": delivery.template_name,
        "activity_id": delivery.activity_id,
        "recipient": delivery.recipient,
        "subject": delivery.subject,
        "message": delivery.message,
        "status": delivery.status,
        "error_message": delivery.error_message,
        "sent_at": delivery.sent_at,
        "created_by": delivery.created_by,
        "created_at": delivery.created_at,
        "notification": notification,
    }


def _get_reminder_plan_or_404(db: Session, plan_id: int) -> models.CRMReminderPlan:
    plan = (
        db.query(models.CRMReminderPlan)
        .filter(models.CRMReminderPlan.id == plan_id)
        .first()
    )
    if not plan:
        raise HTTPException(404, "Relance planifiée introuvable")
    return plan


def _serialize_crm_plan(plan):
    return {
        "id": plan.id,
        "plan_key": plan.plan_key,
        "rule_id": plan.rule_id,
        "rule_name": plan.rule_name,
        "client_id": plan.client_id,
        "client_name": plan.client_name,
        "client_email": plan.client_email,
        "opportunity_id": plan.opportunity_id,
        "opportunity_reference": plan.opportunity_reference,
        "opportunity_title": plan.opportunity_title,
        "assigned_user_id": plan.assigned_user_id,
        "assigned_user_name": plan.assigned_user_name,
        "template_id": plan.template_id,
        "stage_snapshot": plan.stage_snapshot,
        "due_at": plan.due_at,
        "status": plan.status,
        "cancelled_reason": plan.cancelled_reason,
        "sent_delivery_id": plan.sent_delivery_id,
        "created_at": plan.created_at,
        "updated_at": plan.updated_at,
    }


def _crm_reminder_recipient(client: models.Client) -> str:
    direct_email = (client.email or "").strip()
    if direct_email:
        return direct_email
    for contact in sorted(
        client.contacts or [],
        key=lambda item: (not item.is_primary, item.name or "", item.id or 0),
    ):
        contact_email = (contact.email or "").strip()
        if contact_email:
            return contact_email
    return ""


@router.get(
    "/crm/reminder-templates",
    response_model=List[schemas.CRMReminderTemplateResponse],
    dependencies=CRM_VIEW_DEPENDENCIES,
)
def list_crm_reminder_templates(db: Session = Depends(get_db)):
    ensure_default_templates(db)
    return (
        db.query(models.CRMReminderTemplate)
        .filter(models.CRMReminderTemplate.is_active.is_(True))
        .order_by(models.CRMReminderTemplate.name.asc())
        .all()
    )


@router.get(
    "/crm/reminder-rules",
    response_model=List[schemas.CRMReminderRuleResponse],
    dependencies=CRM_VIEW_DEPENDENCIES,
)
def list_crm_reminder_rules(db: Session = Depends(get_db)):
    ensure_default_rules(db)
    return (
        db.query(models.CRMReminderRule)
        .order_by(models.CRMReminderRule.id.asc())
        .all()
    )


@router.patch(
    "/crm/reminder-rules/{rule_id}",
    response_model=schemas.CRMReminderRuleResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def update_crm_reminder_rule(
    rule_id: int,
    item: schemas.CRMReminderRuleUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    security.assert_permission(db, current_user, "SALES_EDIT")
    ensure_default_rules(db)
    rule = (
        db.query(models.CRMReminderRule)
        .filter(models.CRMReminderRule.id == rule_id)
        .first()
    )
    if not rule:
        raise HTTPException(404, "Règle de relance introuvable")
    payload = item.model_dump(exclude_unset=True)
    if "template_id" in payload and payload["template_id"] is not None:
        template = (
            db.query(models.CRMReminderTemplate)
            .filter(
                models.CRMReminderTemplate.id == payload["template_id"],
                models.CRMReminderTemplate.is_active.is_(True),
            )
            .first()
        )
        if not template:
            raise HTTPException(422, "Modèle de relance actif introuvable")
    final_strategy = payload.get("assignment_strategy", rule.assignment_strategy)
    final_user_id = payload.get("fixed_user_id", rule.fixed_user_id)
    if final_strategy == "FIXED_USER":
        owner = (
            db.query(models.User)
            .filter(
                models.User.id == final_user_id,
                models.User.is_active.is_(True),
            )
            .first()
        )
        if not owner:
            raise HTTPException(422, "Sélectionnez un responsable actif")
    else:
        payload["fixed_user_id"] = None
    for field, value in payload.items():
        setattr(rule, field, value)
    db.flush()

    pending_plans = (
        db.query(models.CRMReminderPlan)
        .filter(
            models.CRMReminderPlan.rule_id == rule.id,
            models.CRMReminderPlan.status == "PENDING",
        )
        .all()
    )
    for plan in pending_plans:
        opportunity = plan.opportunity
        entered_at = opportunity.stage_entered_at or opportunity.created_at or utcnow()
        plan.due_at = entered_at + timedelta(days=rule.delay_days)
        plan.assigned_user_id = (
            rule.fixed_user_id
            if rule.assignment_strategy == "FIXED_USER"
            else opportunity.owner_user_id
        )
    db.commit()
    db.refresh(rule)
    return rule


@router.post(
    "/crm/reminder-plans/sync",
    response_model=schemas.CRMReminderSyncResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def synchronize_crm_reminder_plans(
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    return sync_reminder_plans(
        db,
        created_by=current_user.get("sub", "Système"),
        now=utcnow(),
    )


@router.get(
    "/crm/reminder-plans",
    response_model=List[schemas.CRMReminderPlanResponse],
    dependencies=CRM_VIEW_DEPENDENCIES,
)
def list_crm_reminder_plans(
    status: Optional[str] = "PENDING",
    assigned_user_id: Optional[int] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    if not 1 <= limit <= 300:
        raise HTTPException(422, "La limite doit être comprise entre 1 et 300")
    query = db.query(models.CRMReminderPlan)
    if status:
        query = query.filter(
            models.CRMReminderPlan.status == status.strip().upper()
        )
    if assigned_user_id is not None:
        query = query.filter(
            models.CRMReminderPlan.assigned_user_id == assigned_user_id
        )
    return [
        _serialize_crm_plan(plan)
        for plan in query.order_by(
            models.CRMReminderPlan.due_at.asc(),
            models.CRMReminderPlan.id.asc(),
        )
        .limit(limit)
        .all()
    ]


@router.post(
    "/crm/reminder-plans/{plan_id}/cancel",
    response_model=schemas.CRMReminderPlanResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def cancel_crm_reminder_plan(
    plan_id: int,
    item: schemas.CRMReminderPlanCancel,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    plan = _get_reminder_plan_or_404(db, plan_id)
    if plan.status != "PENDING":
        raise HTTPException(409, "Seule une relance en attente peut être ignorée")
    plan.status = "CANCELLED"
    plan.cancelled_reason = (
        f"{item.reason.strip()} · {current_user.get('sub', 'Système')}"
    )
    db.commit()
    db.refresh(plan)
    return _serialize_crm_plan(plan)


@router.post(
    "/crm/reminders/preview",
    response_model=schemas.CRMReminderPreviewResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def preview_crm_reminder(
    item: schemas.CRMReminderPreviewRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    plan = None
    if item.plan_id is not None:
        plan = _get_reminder_plan_or_404(db, item.plan_id)
        if plan.status != "PENDING":
            raise HTTPException(409, "Cette relance planifiée n'est plus en attente")
        if plan.client_id != item.client_id or plan.opportunity_id != item.opportunity_id:
            raise HTTPException(409, "Le contexte ne correspond pas à la relance planifiée")
    client, opportunity = _crm_reminder_context(
        db,
        item.client_id,
        item.opportunity_id,
    )
    template = _crm_reminder_template(
        db,
        item.template_id or (plan.template_id if plan else None),
        item.reminder_kind,
    )
    context = build_template_context(
        client,
        opportunity,
        sender_name=current_user.get("sub", "MMG Menuiseries"),
        due_at=item.due_at,
    )
    try:
        subject, message = render_email(template, context)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "plan_id": plan.id if plan else None,
        "template_id": template.id,
        "template_code": template.code,
        "template_name": template.name,
        "recipient": _crm_reminder_recipient(client),
        "subject": subject,
        "message": message,
        "smtp_configured": bool(_smtp_settings()),
    }


@router.post(
    "/crm/reminders/send",
    response_model=schemas.CRMReminderDeliveryResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def send_crm_reminder(
    item: schemas.CRMReminderSendRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    if not item.confirm_send:
        raise HTTPException(
            409,
            "Confirmez explicitement l'envoi après vérification du destinataire et du message.",
        )
    recipient = item.recipient.strip()
    if "@" not in recipient or recipient.startswith("@") or recipient.endswith("@"):
        raise HTTPException(422, "Adresse email destinataire invalide")
    plan = None
    if item.plan_id is not None:
        plan = _get_reminder_plan_or_404(db, item.plan_id)
        if plan.status != "PENDING":
            raise HTTPException(409, "Cette relance planifiée n'est plus en attente")
        if plan.client_id != item.client_id or plan.opportunity_id != item.opportunity_id:
            raise HTTPException(409, "Le contexte ne correspond pas à la relance planifiée")
    client, opportunity = _crm_reminder_context(
        db,
        item.client_id,
        item.opportunity_id,
    )
    template = None
    if item.template_id is not None:
        template = db.query(models.CRMReminderTemplate).filter(
            models.CRMReminderTemplate.id == item.template_id
        ).first()
        if not template:
            raise HTTPException(404, "Modèle de relance introuvable")

    delivery, notification = record_reminder_delivery(
        db,
        client=client,
        opportunity=opportunity,
        template=template,
        plan=plan,
        reminder_key=item.reminder_key,
        recipient=recipient,
        subject=item.subject,
        message=item.message,
        created_by=current_user.get("sub", "Système"),
        send_email=_send_smtp_email,
    )

    db.commit()
    db.refresh(delivery)
    return _serialize_crm_delivery(delivery, notification)


@router.get(
    "/crm/reminders/history",
    response_model=List[schemas.CRMReminderDeliveryResponse],
    dependencies=CRM_VIEW_DEPENDENCIES,
)
def list_crm_reminder_history(
    client_id: Optional[int] = None,
    opportunity_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    if not 1 <= limit <= 200:
        raise HTTPException(422, "La limite doit être comprise entre 1 et 200")
    query = db.query(models.CRMReminderDelivery)
    if client_id is not None:
        query = query.filter(models.CRMReminderDelivery.client_id == client_id)
    if opportunity_id is not None:
        query = query.filter(
            models.CRMReminderDelivery.opportunity_id == opportunity_id
        )
    if status:
        query = query.filter(
            models.CRMReminderDelivery.status == status.strip().upper()
        )
    return [
        _serialize_crm_delivery(item)
        for item in query.order_by(models.CRMReminderDelivery.created_at.desc())
        .limit(limit)
        .all()
    ]


@router.get(
    "/opportunities",
    response_model=List[schemas.CRMOpportunityResponse],
    dependencies=CRM_VIEW_DEPENDENCIES,
)
def list_crm_opportunities(
    client_id: Optional[int] = None,
    site_address_id: Optional[int] = None,
    owner_user_id: Optional[int] = None,
    sale_order_id: Optional[int] = None,
    stage: Optional[schemas.CRMOpportunityStage] = None,
    need_type: Optional[schemas.CRMNeedType] = None,
    origin: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.CRMOpportunity)
    if client_id is not None:
        query = query.filter(models.CRMOpportunity.client_id == client_id)
    if site_address_id is not None:
        query = query.filter(models.CRMOpportunity.site_address_id == site_address_id)
    if owner_user_id is not None:
        query = query.filter(models.CRMOpportunity.owner_user_id == owner_user_id)
    if sale_order_id is not None:
        query = query.filter(models.CRMOpportunity.sale_order_id == sale_order_id)
    if stage is not None:
        query = query.filter(models.CRMOpportunity.stage == stage.value)
    if need_type is not None:
        query = query.filter(models.CRMOpportunity.need_type == need_type.value)
    if origin:
        query = query.filter(func.lower(models.CRMOpportunity.origin) == origin.strip().lower())
    if search:
        pattern = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(models.CRMOpportunity.reference).like(pattern),
                func.lower(models.CRMOpportunity.title).like(pattern),
            )
        )
    return query.order_by(models.CRMOpportunity.created_at.desc()).all()


@router.post(
    "/opportunities",
    response_model=schemas.CRMOpportunityResponse,
    status_code=201,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def create_crm_opportunity(
    item: schemas.CRMOpportunityCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    if item.stage != schemas.CRMOpportunityStage.NEW:
        raise HTTPException(
            409,
            (
                "Une opportunité entre toujours par « Nouveau besoin ». "
                "Les étapes suivantes sont calculées depuis les actions métier."
            ),
        )
    _validate_opportunity_links(
        db,
        item.client_id,
        item.site_address_id,
        item.owner_user_id,
        item.sale_order_id,
    )
    if item.stage == schemas.CRMOpportunityStage.LOST and not (item.loss_reason or "").strip():
        raise HTTPException(422, "Un motif de perte est obligatoire")
    if item.sale_order_id and item.stage != schemas.CRMOpportunityStage.WON:
        raise HTTPException(422, "Le devis converti ne peut être lié qu'à une opportunité gagnée")
    now = utcnow()
    opportunity = models.CRMOpportunity(
        reference=f"OPP-TMP-{uuid.uuid4().hex}",
        client_id=item.client_id,
        site_address_id=item.site_address_id,
        owner_user_id=item.owner_user_id,
        sale_order_id=item.sale_order_id,
        title=item.title.strip(),
        origin=item.origin.strip() if item.origin else None,
        need_type=item.need_type.value,
        stage=item.stage.value,
        estimated_amount=item.estimated_amount,
        probability=item.probability,
        next_milestone=item.next_milestone,
        next_milestone_at=item.next_milestone_at,
        expected_close_date=item.expected_close_date,
        loss_reason=item.loss_reason,
        won_at=now if item.stage == schemas.CRMOpportunityStage.WON else None,
        lost_at=now if item.stage == schemas.CRMOpportunityStage.LOST else None,
        created_by=current_user.get("sub", "Système"),
    )
    db.add(opportunity)
    db.flush()
    opportunity.reference = f"OPP-{now.year}-{opportunity.id:05d}"
    db.add(
        models.CRMOpportunityStageHistory(
            opportunity_id=opportunity.id,
            from_stage=None,
            to_stage=opportunity.stage,
            changed_by=current_user.get("sub", "Système"),
            changed_at=now,
        )
    )
    db.commit()
    db.refresh(opportunity)
    return opportunity


@router.get(
    "/opportunities/{opportunity_id}",
    response_model=schemas.CRMOpportunityResponse,
    dependencies=CRM_VIEW_DEPENDENCIES,
)
def get_crm_opportunity(opportunity_id: int, db: Session = Depends(get_db)):
    return _get_opportunity_or_404(db, opportunity_id)


@router.patch(
    "/opportunities/{opportunity_id}",
    response_model=schemas.CRMOpportunityResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def update_crm_opportunity(
    opportunity_id: int,
    item: schemas.CRMOpportunityUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    opportunity = _get_opportunity_or_404(db, opportunity_id)
    previous_stage = opportunity.stage
    payload = item.model_dump(exclude_unset=True)
    target_stage = payload.get("stage")
    target_stage = target_stage.value if target_stage is not None else opportunity.stage
    stage_changed = target_stage != opportunity.stage
    if stage_changed:
        if target_stage in OPPORTUNITY_DERIVED_STAGES:
            raise HTTPException(
                409,
                (
                    "Cette étape dépend d'une action métier. Utilisez la qualification, "
                    "la mission de métré, le dossier technique ou le devis lié."
                ),
            )
        if target_stage not in OPPORTUNITY_TRANSITIONS.get(opportunity.stage, set()):
            raise HTTPException(
                409,
                f"Transition d'opportunité interdite: {opportunity.stage} → {target_stage}",
            )
    final_site_id = payload.get("site_address_id", opportunity.site_address_id)
    final_owner_id = payload.get("owner_user_id", opportunity.owner_user_id)
    final_sale_order_id = payload.get("sale_order_id", opportunity.sale_order_id)
    _validate_opportunity_links(
        db,
        opportunity.client_id,
        final_site_id,
        final_owner_id,
        final_sale_order_id,
    )
    final_loss_reason = payload.get("loss_reason", opportunity.loss_reason)
    if target_stage == models.CRMOpportunityStage.LOST.value and not (final_loss_reason or "").strip():
        raise HTTPException(422, "Un motif de perte est obligatoire")
    if final_sale_order_id and target_stage != models.CRMOpportunityStage.WON.value:
        raise HTTPException(422, "Le devis converti ne peut être lié qu'à une opportunité gagnée")
    for field, value in payload.items():
        if hasattr(value, "value"):
            value = value.value
        setattr(opportunity, field, value)
    if stage_changed:
        stage_changed_at = utcnow()
        opportunity.stage_entered_at = stage_changed_at
        db.add(
            models.CRMOpportunityStageHistory(
                opportunity_id=opportunity.id,
                from_stage=previous_stage,
                to_stage=target_stage,
                changed_by=current_user.get("sub", "Système"),
                changed_at=stage_changed_at,
            )
        )
        (
            db.query(models.CRMReminderPlan)
            .filter(
                models.CRMReminderPlan.opportunity_id == opportunity.id,
                models.CRMReminderPlan.status == "PENDING",
            )
            .update(
                {
                    models.CRMReminderPlan.status: "CANCELLED",
                    models.CRMReminderPlan.cancelled_reason: "Étape commerciale modifiée",
                },
                synchronize_session=False,
            )
        )
    if target_stage == models.CRMOpportunityStage.WON.value and opportunity.won_at is None:
        opportunity.won_at = utcnow()
    if target_stage == models.CRMOpportunityStage.LOST.value and opportunity.lost_at is None:
        opportunity.lost_at = utcnow()
    if target_stage != models.CRMOpportunityStage.LOST.value:
        opportunity.lost_at = None
        opportunity.loss_reason = None
    db.commit()
    db.refresh(opportunity)
    return opportunity


@router.post(
    "/opportunities/{opportunity_id}/qualify",
    response_model=schemas.CRMOpportunityQualificationResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def qualify_crm_opportunity(
    opportunity_id: int,
    item: schemas.CRMOpportunityQualificationRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    opportunity = _get_opportunity_or_404(db, opportunity_id)
    if opportunity.stage not in {
        models.CRMOpportunityStage.NEW.value,
        models.CRMOpportunityStage.LOST.value,
    }:
        raise HTTPException(409, "Cette opportunité a déjà été qualifiée")

    site = None
    if item.site_address_id:
        site = (
            db.query(models.ClientSiteAddress)
            .filter(models.ClientSiteAddress.id == item.site_address_id)
            .first()
        )
        if not site or site.client_id != opportunity.client_id:
            raise HTTPException(400, "Le chantier sélectionné n'appartient pas au client")
    if (
        item.project_scope == schemas.CRMProjectScope.SUPPLY_AND_INSTALL
        and not site
    ):
        raise HTTPException(422, "Sélectionnez une adresse chantier pour une fourniture avec pose")
    if (
        item.study_route == schemas.CRMStudyRoute.DIRECT_QUOTE
        and item.project_scope == schemas.CRMProjectScope.SUPPLY_AND_INSTALL
    ):
        raise HTTPException(
            422,
            "Une fourniture avec pose doit passer par un dossier de cotes et un contrôle BE",
        )

    actor = current_user.get("sub", "Système")
    opportunity.need_type = item.need_type.value
    opportunity.site_address_id = site.id if site else None
    opportunity.estimated_amount = item.estimated_amount
    opportunity.expected_close_date = item.expected_close_date
    opportunity.lost_at = None
    opportunity.loss_reason = None

    mission = None
    if item.study_route != schemas.CRMStudyRoute.DIRECT_QUOTE:
        set_opportunity_stage(
            db,
            opportunity,
            models.CRMOpportunityStage.QUALIFIED.value,
            actor,
            next_milestone="Créer et instruire le dossier de cotes",
            allow_regression=True,
        )
        mission = (
            db.query(models.MeasureMission)
            .filter(
                models.MeasureMission.opportunity_id == opportunity.id,
                models.MeasureMission.status != models.MeasureMissionStatus.CANCELLED.value,
            )
            .order_by(models.MeasureMission.created_at.desc())
            .first()
        )
        if not mission:
            source_type = item.study_route.value
            mission = models.MeasureMission(
                reference=next_number(db, "measure_mission"),
                client_id=opportunity.client_id,
                site_address_id=site.id if site else None,
                opportunity_id=opportunity.id,
                status=(
                    models.MeasureMissionStatus.TO_SCHEDULE.value
                    if source_type == schemas.CRMStudyRoute.SITE_VISIT.value
                    else models.MeasureMissionStatus.DRAFT.value
                ),
                source_type=source_type,
                project_scope=item.project_scope.value,
                verification_status=schemas.MeasureVerificationStatus.UNVERIFIED.value,
                purpose=opportunity.title,
                notes=item.qualification_note.strip(),
                created_by=actor,
            )
            db.add(mission)
            db.flush()
        sync_opportunity_from_mission(db, mission, actor)
    else:
        set_opportunity_stage(
            db,
            opportunity,
            models.CRMOpportunityStage.QUALIFIED.value,
            actor,
            next_milestone="Composer la proposition commerciale depuis la fiche client",
            allow_regression=True,
        )

    db.add(
        models.CRMActivity(
            client_id=opportunity.client_id,
            opportunity_id=opportunity.id,
            assigned_user_id=opportunity.owner_user_id,
            activity_type=models.CRMActivityType.NOTE.value,
            subject="Qualification commerciale validée",
            note=(
                f"Parcours: {item.study_route.value}. "
                f"Périmètre: {item.project_scope.value}. "
                f"{item.qualification_note.strip()}"
            ),
            status=models.CRMActivityStatus.COMPLETED.value,
            author=actor,
            completed_at=utcnow(),
        )
    )
    db.commit()
    db.refresh(opportunity)
    return {
        "opportunity": opportunity,
        "mission_id": mission.id if mission else None,
        "study_route": item.study_route,
    }


@router.post(
    "/crm/cockpit/opportunities/{opportunity_id}/assign-owner",
    response_model=schemas.CRMOpportunityResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def assign_crm_opportunity_owner(
    opportunity_id: int,
    item: schemas.CRMCockpitAssignOwnerRequest,
    db: Session = Depends(get_db),
):
    opportunity = _get_opportunity_or_404(db, opportunity_id)
    _validate_opportunity_links(
        db,
        opportunity.client_id,
        opportunity.site_address_id,
        item.owner_user_id,
        opportunity.sale_order_id,
    )
    opportunity.owner_user_id = item.owner_user_id
    (
        db.query(models.CRMReminderPlan)
        .filter(
            models.CRMReminderPlan.opportunity_id == opportunity.id,
            models.CRMReminderPlan.status == "PENDING",
        )
        .update(
            {models.CRMReminderPlan.assigned_user_id: item.owner_user_id},
            synchronize_session=False,
        )
    )
    db.commit()
    db.refresh(opportunity)
    return opportunity


@router.post(
    "/crm/cockpit/opportunities/{opportunity_id}/schedule-action",
    response_model=schemas.CRMActivityResponse,
    status_code=201,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def schedule_crm_opportunity_action(
    opportunity_id: int,
    item: schemas.CRMCockpitScheduleActionRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    opportunity = _get_opportunity_or_404(db, opportunity_id)
    if opportunity.stage in {
        models.CRMOpportunityStage.WON.value,
        models.CRMOpportunityStage.LOST.value,
    }:
        raise HTTPException(
            409,
            "Une opportunité gagnée ou perdue ne peut plus recevoir de prochaine action",
        )

    subject = item.subject.strip()
    activity = models.CRMActivity(
        client_id=opportunity.client_id,
        opportunity_id=opportunity.id,
        activity_type=item.activity_type.value,
        subject=subject,
        note=item.note.strip() if item.note else None,
        due_at=item.due_at,
        status=models.CRMActivityStatus.TODO.value,
        author=current_user.get("sub", "Système"),
    )
    opportunity.next_milestone = subject
    opportunity.next_milestone_at = item.due_at
    if item.reminder_plan_id is not None:
        reminder_plan = (
            db.query(models.CRMReminderPlan)
            .filter(
                models.CRMReminderPlan.id == item.reminder_plan_id,
                models.CRMReminderPlan.opportunity_id == opportunity.id,
                models.CRMReminderPlan.status == "PENDING",
            )
            .first()
        )
        if not reminder_plan:
            raise HTTPException(409, "La relance planifiée n'est plus disponible")
        reminder_plan.status = "CANCELLED"
        reminder_plan.cancelled_reason = "Convertie en action commerciale"
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity


@router.delete(
    "/opportunities/{opportunity_id}",
    status_code=204,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def delete_crm_opportunity(opportunity_id: int, db: Session = Depends(get_db)):
    opportunity = _get_opportunity_or_404(db, opportunity_id)
    db.delete(opportunity)
    db.commit()


@router.get(
    "/activities",
    response_model=List[schemas.CRMActivityResponse],
    dependencies=CRM_VIEW_DEPENDENCIES,
)
def list_crm_activities(
    client_id: Optional[int] = None,
    opportunity_id: Optional[int] = None,
    activity_type: Optional[schemas.CRMActivityType] = None,
    status: Optional[schemas.CRMActivityStatus] = None,
    author: Optional[str] = None,
    due_from: Optional[datetime] = None,
    due_to: Optional[datetime] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.CRMActivity)
    if client_id is not None:
        query = query.filter(models.CRMActivity.client_id == client_id)
    if opportunity_id is not None:
        query = query.filter(models.CRMActivity.opportunity_id == opportunity_id)
    if activity_type is not None:
        query = query.filter(models.CRMActivity.activity_type == activity_type.value)
    if status is not None:
        query = query.filter(models.CRMActivity.status == status.value)
    if author:
        query = query.filter(func.lower(models.CRMActivity.author) == author.strip().lower())
    if due_from is not None:
        query = query.filter(models.CRMActivity.due_at >= due_from)
    if due_to is not None:
        query = query.filter(models.CRMActivity.due_at <= due_to)
    if search:
        pattern = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(models.CRMActivity.subject).like(pattern),
                func.lower(func.coalesce(models.CRMActivity.note, "")).like(pattern),
            )
        )
    return query.order_by(models.CRMActivity.created_at.desc()).all()


@router.post(
    "/activities",
    response_model=schemas.CRMActivityResponse,
    status_code=201,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def create_crm_activity(
    item: schemas.CRMActivityCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    _validate_activity_links(db, item.client_id, item.opportunity_id)
    activity = models.CRMActivity(
        client_id=item.client_id,
        opportunity_id=item.opportunity_id,
        activity_type=item.activity_type.value,
        subject=item.subject.strip(),
        note=item.note,
        due_at=item.due_at,
        status=item.status.value,
        author=current_user.get("sub", "Système"),
        completed_at=utcnow() if item.status == schemas.CRMActivityStatus.COMPLETED else None,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity


@router.get(
    "/activities/{activity_id}",
    response_model=schemas.CRMActivityResponse,
    dependencies=CRM_VIEW_DEPENDENCIES,
)
def get_crm_activity(activity_id: int, db: Session = Depends(get_db)):
    return _get_activity_or_404(db, activity_id)


@router.patch(
    "/activities/{activity_id}",
    response_model=schemas.CRMActivityResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def update_crm_activity(
    activity_id: int,
    item: schemas.CRMActivityUpdate,
    db: Session = Depends(get_db),
):
    activity = _get_activity_or_404(db, activity_id)
    payload = item.model_dump(exclude_unset=True)
    target_status = payload.get("status")
    target_status = target_status.value if target_status is not None else activity.status
    if target_status != activity.status:
        if target_status not in ACTIVITY_TRANSITIONS.get(activity.status, set()):
            raise HTTPException(
                409,
                f"Transition d'activité interdite: {activity.status} → {target_status}",
            )
    final_opportunity_id = payload.get("opportunity_id", activity.opportunity_id)
    _validate_activity_links(db, activity.client_id, final_opportunity_id)
    for field, value in payload.items():
        if hasattr(value, "value"):
            value = value.value
        setattr(activity, field, value)
    if target_status == models.CRMActivityStatus.COMPLETED.value and activity.completed_at is None:
        activity.completed_at = utcnow()
    if target_status != models.CRMActivityStatus.COMPLETED.value:
        activity.completed_at = None
    db.commit()
    db.refresh(activity)
    return activity


@router.delete(
    "/activities/{activity_id}",
    status_code=204,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def delete_crm_activity(activity_id: int, db: Session = Depends(get_db)):
    activity = _get_activity_or_404(db, activity_id)
    db.delete(activity)
    db.commit()


@router.get(
    "/sites",
    response_model=List[schemas.ClientSiteAddressResponse],
    dependencies=CRM_VIEW_DEPENDENCIES,
)
def list_client_sites(client_id: int, db: Session = Depends(get_db)):
    client = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not client:
        raise HTTPException(404, "Client introuvable")
    return (
        db.query(models.ClientSiteAddress)
        .filter(models.ClientSiteAddress.client_id == client_id)
        .order_by(models.ClientSiteAddress.is_default.desc(), models.ClientSiteAddress.created_at.desc())
        .all()
    )


@router.post(
    "/sites",
    response_model=schemas.ClientSiteAddressResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def create_client_site(item: schemas.ClientSiteAddressCreate, db: Session = Depends(get_db)):
    if not item.client_id:
        raise HTTPException(422, "client_id est obligatoire")
    client = db.query(models.Client).filter(models.Client.id == item.client_id).first()
    if not client:
        raise HTTPException(404, "Client introuvable")
    site = _resolve_site(db, item.client_id, site_data=item)
    db.commit()
    db.refresh(site)
    return site


@router.put(
    "/sites/{site_id}",
    response_model=schemas.ClientSiteAddressResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def update_client_site(
    site_id: int,
    item: schemas.ClientSiteAddressCreate,
    db: Session = Depends(get_db),
):
    site = db.query(models.ClientSiteAddress).filter(models.ClientSiteAddress.id == site_id).first()
    if not site:
        raise HTTPException(404, "Adresse chantier introuvable")
    if item.client_id and item.client_id != site.client_id:
        raise HTTPException(400, "Une adresse chantier ne peut pas changer de client")
    if item.is_default:
        db.query(models.ClientSiteAddress).filter(
            models.ClientSiteAddress.client_id == site.client_id,
            models.ClientSiteAddress.id != site.id,
        ).update({"is_default": False}, synchronize_session=False)
    for field, value in item.model_dump(exclude={"client_id"}).items():
        setattr(site, field, value)
    db.commit()
    db.refresh(site)
    return site


@router.get("/missions", response_model=List[schemas.MeasureMissionResponse])
def list_measure_missions(
    client_id: Optional[int] = None,
    opportunity_id: Optional[int] = None,
    assigned_user_id: Optional[int] = None,
    status: Optional[schemas.MeasureMissionStatus] = None,
    scheduled_from: Optional[datetime] = None,
    scheduled_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.MeasureMission)
    if client_id:
        query = query.filter(models.MeasureMission.client_id == client_id)
    if opportunity_id:
        query = query.filter(models.MeasureMission.opportunity_id == opportunity_id)
    if assigned_user_id:
        query = query.filter(models.MeasureMission.assigned_user_id == assigned_user_id)
    if status:
        query = query.filter(models.MeasureMission.status == status.value)
    if scheduled_from:
        query = query.filter(models.MeasureMission.scheduled_start >= scheduled_from)
    if scheduled_to:
        query = query.filter(models.MeasureMission.scheduled_start < scheduled_to)
    missions = query.order_by(
        models.MeasureMission.scheduled_start.asc().nullslast(),
        models.MeasureMission.created_at.desc(),
    ).all()
    return [_serialize_mission(mission) for mission in missions]


@router.post(
    "/missions",
    response_model=schemas.MeasureMissionResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def create_measure_mission(
    item: schemas.MeasureMissionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    client = db.query(models.Client).filter(models.Client.id == item.client_id).first()
    if not client:
        raise HTTPException(404, "Client introuvable")
    site = _resolve_site(db, item.client_id, item.site_address_id, item.site)
    opportunity = None
    if item.opportunity_id:
        opportunity = _get_opportunity_or_404(db, item.opportunity_id)
        if opportunity.client_id != item.client_id:
            raise HTTPException(400, "La mission et l'opportunité doivent appartenir au même client")
    if item.sale_order_id and not db.query(models.SaleOrder).filter(models.SaleOrder.id == item.sale_order_id).first():
        raise HTTPException(404, "Devis introuvable")
    if (
        opportunity
        and opportunity.sale_order_id
        and item.sale_order_id
        and opportunity.sale_order_id != item.sale_order_id
    ):
        raise HTTPException(400, "Le devis de la mission diffère de celui de l'opportunité")
    if item.assigned_user_id:
        assigned_user = db.query(models.User).filter(models.User.id == item.assigned_user_id).first()
        if not assigned_user or not assigned_user.is_active:
            raise HTTPException(400, "Technicien introuvable ou inactif")
    if item.status == schemas.MeasureMissionStatus.SCHEDULED:
        if item.source_type != schemas.MeasureSourceType.SITE_VISIT:
            raise HTTPException(422, "Seul un relevé MMG sur chantier doit être planifié")
        if not site:
            raise HTTPException(422, "Une adresse chantier est obligatoire pour planifier la mission")
        if not item.assigned_user_id or not item.scheduled_start:
            raise HTTPException(422, "Affectez un métreur et une date avant de planifier")
    if item.scheduled_start and item.scheduled_end and item.scheduled_end <= item.scheduled_start:
        raise HTTPException(422, "La fin planifiée doit être postérieure au début")
    project_scope = item.project_scope
    if project_scope is None:
        project_scope = (
            schemas.MeasureProjectScope.SUPPLY_AND_INSTALL
            if item.source_type == schemas.MeasureSourceType.SITE_VISIT
            else schemas.MeasureProjectScope.SUPPLY_ONLY
        )
    mission = models.MeasureMission(
        reference=next_number(db, "measure_mission"),
        client_id=item.client_id,
        site_address_id=site.id if site else None,
        opportunity_id=item.opportunity_id,
        sale_order_id=item.sale_order_id,
        assigned_user_id=item.assigned_user_id,
        status=item.status.value,
        source_type=item.source_type.value,
        project_scope=project_scope.value,
        verification_status=schemas.MeasureVerificationStatus.UNVERIFIED.value,
        purpose=item.purpose,
        scheduled_start=item.scheduled_start,
        scheduled_end=item.scheduled_end,
        notes=item.notes,
        created_by=current_user.get("sub", "Système"),
    )
    db.add(mission)
    db.flush()
    sync_opportunity_from_mission(
        db,
        mission,
        current_user.get("sub", "Système"),
    )
    db.commit()
    db.refresh(mission)
    return _serialize_mission(mission)


@router.get("/missions/{mission_id}", response_model=schemas.MeasureMissionResponse)
def get_measure_mission(mission_id: int, db: Session = Depends(get_db)):
    mission = _get_mission_or_404(db, mission_id)
    return _serialize_mission(mission)


@router.put(
    "/missions/{mission_id}",
    response_model=schemas.MeasureMissionResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def update_measure_mission(
    mission_id: int,
    item: schemas.MeasureMissionUpdate,
    db: Session = Depends(get_db),
):
    mission = _get_mission_or_404(db, mission_id)
    _ensure_mission_editable(mission)
    payload = item.model_dump(exclude_unset=True)
    site_data = payload.pop("site", None)
    site_address_id = payload.pop("site_address_id", None)
    opportunity_marker = object()
    opportunity_id = payload.pop("opportunity_id", opportunity_marker)
    if site_data is not None or site_address_id is not None:
        site_schema = schemas.ClientSiteAddressCreate(**site_data) if site_data else None
        site = _resolve_site(db, mission.client_id, site_address_id, site_schema)
        mission.site_address_id = site.id if site else None
    if opportunity_id is not opportunity_marker:
        if opportunity_id is None:
            mission.opportunity_id = None
        else:
            opportunity = _get_opportunity_or_404(db, opportunity_id)
            if opportunity.client_id != mission.client_id:
                raise HTTPException(
                    400,
                    "La mission et l'opportunité doivent appartenir au même client",
                )
            if (
                opportunity.sale_order_id
                and mission.sale_order_id
                and opportunity.sale_order_id != mission.sale_order_id
            ):
                raise HTTPException(400, "Le devis de la mission diffère de celui de l'opportunité")
            mission.opportunity_id = opportunity.id
    if "assigned_user_id" in payload and payload["assigned_user_id"] is not None:
        assigned_user = (
            db.query(models.User)
            .filter(models.User.id == payload["assigned_user_id"], models.User.is_active.is_(True))
            .first()
        )
        if not assigned_user:
            raise HTTPException(400, "Métreur introuvable ou inactif")
    for field, value in payload.items():
        setattr(mission, field, value)
    if mission.scheduled_start and mission.scheduled_end and mission.scheduled_end <= mission.scheduled_start:
        raise HTTPException(422, "La fin planifiée doit être postérieure au début")
    if (
        mission.source_type == schemas.MeasureSourceType.SITE_VISIT.value
        and mission.scheduled_start
        and mission.assigned_user_id
        and mission.status in {
            models.MeasureMissionStatus.DRAFT.value,
            models.MeasureMissionStatus.TO_SCHEDULE.value,
        }
    ):
        mission.status = models.MeasureMissionStatus.SCHEDULED.value
    db.commit()
    db.refresh(mission)
    return _serialize_mission(mission)


@router.get(
    "/missions/{mission_id}/openings",
    response_model=List[schemas.MeasureOpeningResponse],
)
def list_measure_openings(mission_id: int, db: Session = Depends(get_db)):
    mission = _get_mission_or_404(db, mission_id)
    return mission.openings


@router.post(
    "/missions/{mission_id}/openings",
    response_model=schemas.MeasureOpeningResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def create_measure_opening(
    mission_id: int,
    item: schemas.MeasureOpeningCreate,
    db: Session = Depends(get_db),
):
    mission = _get_mission_or_404(db, mission_id)
    _ensure_mission_editable(mission)
    sequence = item.sequence
    if sequence is None:
        sequence = (
            db.query(func.max(models.MeasureOpening.sequence))
            .filter(models.MeasureOpening.mission_id == mission_id)
            .scalar()
            or 0
        ) + 1
    if db.query(models.MeasureOpening).filter_by(mission_id=mission_id, sequence=sequence).first():
        raise HTTPException(409, "Ce numéro d'ouvrage existe déjà dans la mission")
    opening_payload = item.model_dump(exclude={"sequence"})
    opening_payload["status"] = item.status.value
    opening = models.MeasureOpening(
        mission_id=mission_id,
        sequence=sequence,
        **opening_payload,
    )
    _validate_opening_dimensions(opening)
    db.add(opening)
    db.commit()
    db.refresh(opening)
    return opening


@router.put(
    "/missions/{mission_id}/openings/{opening_id}",
    response_model=schemas.MeasureOpeningResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def update_measure_opening(
    mission_id: int,
    opening_id: int,
    item: schemas.MeasureOpeningUpdate,
    db: Session = Depends(get_db),
):
    mission = _get_mission_or_404(db, mission_id)
    _ensure_mission_editable(mission)
    opening = (
        db.query(models.MeasureOpening)
        .filter(
            models.MeasureOpening.id == opening_id,
            models.MeasureOpening.mission_id == mission_id,
        )
        .first()
    )
    if not opening:
        raise HTTPException(404, "Ouvrage introuvable")
    payload = item.model_dump(exclude_unset=True)
    if item.status is not None:
        payload["status"] = item.status.value
    for field, value in payload.items():
        setattr(opening, field, value)
    _validate_opening_dimensions(opening)
    db.commit()
    db.refresh(opening)
    return opening


@router.delete(
    "/missions/{mission_id}/openings/{opening_id}",
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def delete_measure_opening(
    mission_id: int,
    opening_id: int,
    db: Session = Depends(get_db),
):
    mission = _get_mission_or_404(db, mission_id)
    _ensure_mission_editable(mission)
    opening = (
        db.query(models.MeasureOpening)
        .filter(
            models.MeasureOpening.id == opening_id,
            models.MeasureOpening.mission_id == mission_id,
        )
        .first()
    )
    if not opening:
        raise HTTPException(404, "Ouvrage introuvable")
    db.delete(opening)
    db.commit()
    return {"status": "deleted"}


@router.patch(
    "/missions/{mission_id}/status",
    response_model=schemas.MeasureMissionResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def update_measure_mission_status(
    mission_id: int,
    item: schemas.MeasureMissionStatusUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    mission = _get_mission_or_404(db, mission_id)
    target = item.status.value
    if target == mission.status:
        return _serialize_mission(mission)
    if target not in MISSION_TRANSITIONS.get(mission.status, set()):
        raise HTTPException(
            409,
            f"Transition de mission interdite: {mission.status} → {target}",
        )
    if target == models.MeasureMissionStatus.SCHEDULED.value:
        if mission.source_type != schemas.MeasureSourceType.SITE_VISIT.value:
            raise HTTPException(422, "Ce dossier de cotes ne nécessite pas de mission sur chantier")
        if not mission.site_address_id:
            raise HTTPException(422, "Une adresse chantier est obligatoire pour planifier la mission")
        if not mission.assigned_user_id or not mission.scheduled_start:
            raise HTTPException(422, "Affectez un métreur et une date avant de planifier")
    if target == models.MeasureMissionStatus.TO_REVIEW.value:
        if (
            mission.source_type == schemas.MeasureSourceType.CLIENT_DOCUMENTS.value
            and not mission.source_documents
        ):
            raise HTTPException(422, "Joignez au moins un plan ou croquis fourni par le client")
        if not mission.openings:
            raise HTTPException(422, "Ajoutez au moins un ouvrage avant le contrôle BE")
        incomplete = [
            opening
            for opening in mission.openings
            if opening.status not in {
                schemas.MeasureOpeningStatus.COMPLETE.value,
                schemas.MeasureOpeningStatus.TO_REVIEW.value,
            }
        ]
        if incomplete:
            raise HTTPException(422, "Tous les ouvrages doivent être terminés avant le contrôle BE")
        for opening in mission.openings:
            _validate_opening_dimensions(opening)
            opening.status = schemas.MeasureOpeningStatus.TO_REVIEW.value
    if target in {
        models.MeasureMissionStatus.VALIDATED.value,
        models.MeasureMissionStatus.CORRECTION_REQUIRED.value,
    }:
        if not (_current_roles(current_user) & BE_REVIEW_ROLES):
            raise HTTPException(403, "Le contrôle BE est réservé aux profils habilités")
        if target == models.MeasureMissionStatus.VALIDATED.value:
            if not mission.openings:
                raise HTTPException(422, "Aucun ouvrage à valider")
            for opening in mission.openings:
                _validate_opening_dimensions(opening)
                opening.status = schemas.MeasureOpeningStatus.VALIDATED.value
            if mission.source_type == schemas.MeasureSourceType.SITE_VISIT.value:
                mission.verification_status = schemas.MeasureVerificationStatus.READY_FOR_FABRICATION.value
                mission.site_verified_at = utcnow()
                mission.site_verified_by = current_user.get("sub", "Système")
            elif mission.project_scope == schemas.MeasureProjectScope.SUPPLY_ONLY.value:
                mission.verification_status = schemas.MeasureVerificationStatus.CLIENT_APPROVAL_REQUIRED.value
            else:
                mission.verification_status = schemas.MeasureVerificationStatus.SITE_VERIFICATION_REQUIRED.value
            _get_or_create_technical_dossier(
                db,
                mission,
                current_user.get("sub", "Système"),
            )
        else:
            mission.verification_status = schemas.MeasureVerificationStatus.UNVERIFIED.value
            for opening in mission.openings:
                if opening.status != schemas.MeasureOpeningStatus.VALIDATED.value:
                    opening.status = schemas.MeasureOpeningStatus.CORRECTION_REQUIRED.value
    mission.status = target
    sync_opportunity_from_mission(
        db,
        mission,
        current_user.get("sub", "Système"),
    )
    db.commit()
    db.refresh(mission)
    return _serialize_mission(mission)


@router.get(
    "/missions/{mission_id}/technical-dossier",
    response_model=schemas.TechnicalDossierResponse,
)
def get_measure_technical_dossier(
    mission_id: int,
    db: Session = Depends(get_db),
):
    mission = _get_mission_or_404(db, mission_id)
    if not mission.technical_dossier:
        raise HTTPException(404, "Le dossier technique n'a pas encore été créé")
    return mission.technical_dossier


@router.post(
    "/missions/{mission_id}/technical-dossier",
    response_model=schemas.TechnicalDossierResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def create_measure_technical_dossier(
    mission_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    _assert_technical_edit(db, current_user)
    mission = _get_mission_or_404(db, mission_id)
    if mission.status not in {
        models.MeasureMissionStatus.VALIDATED.value,
        models.MeasureMissionStatus.QUOTED.value,
    }:
        raise HTTPException(409, "Validez d'abord le métré et ses ouvrages")
    dossier = _get_or_create_technical_dossier(
        db,
        mission,
        current_user.get("sub", "Système"),
    )
    db.commit()
    db.refresh(dossier)
    return dossier


@router.post(
    "/missions/{mission_id}/technical-dossier/versions",
    response_model=schemas.TechnicalDossierResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
async def upload_measure_technical_version(
    mission_id: int,
    document_type: str = Form(...),
    source_system: str = Form(...),
    source_reference: Optional[str] = Form(None),
    opening_ids: str = Form(""),
    notes: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    _assert_technical_edit(db, current_user)
    mission = _get_mission_or_404(db, mission_id)
    if mission.status not in {
        models.MeasureMissionStatus.VALIDATED.value,
        models.MeasureMissionStatus.QUOTED.value,
    }:
        raise HTTPException(409, "Validez d'abord le métré et ses ouvrages")
    dossier = _get_or_create_technical_dossier(
        db,
        mission,
        current_user.get("sub", "Système"),
    )
    try:
        normalized_type = schemas.TechnicalDocumentType(document_type.upper()).value
    except ValueError as exc:
        raise HTTPException(422, "Type de document technique invalide") from exc
    is_quoting = normalized_type == schemas.TechnicalDocumentType.QUOTING.value
    if not is_quoting and not _sale_is_signed(mission):
        raise HTTPException(
            409,
            "Les fichiers de fabrication et de débit ne sont acceptés qu'après signature du devis client",
        )
    status_field = "quoting_status" if is_quoting else "production_status"
    current_status = getattr(dossier, status_field)
    editable_statuses = {
        schemas.TechnicalDossierStatus.DRAFT.value,
        schemas.TechnicalDossierStatus.CORRECTION_REQUIRED.value,
        schemas.TechnicalDossierStatus.LOCKED.value if not is_quoting else "",
    }
    if not is_quoting and dossier.launched_at:
        editable_statuses.add(schemas.TechnicalDossierStatus.VALIDATED.value)
    if current_status not in editable_statuses:
        raise HTTPException(
            409,
            "Cette phase doit être en brouillon ou à corriger pour ajouter une version",
        )
    requested_source = source_system.upper().strip()
    if requested_source == "AUTO":
        normalized_source = ""
    else:
        try:
            normalized_source = schemas.TechnicalSourceSystem(requested_source).value
        except ValueError as exc:
            raise HTTPException(422, "Logiciel source invalide") from exc

    parsed_opening_ids = []
    if opening_ids.strip():
        try:
            parsed_opening_ids = [
                int(value.strip())
                for value in opening_ids.split(",")
                if value.strip()
            ]
        except ValueError as exc:
            raise HTTPException(422, "La liste des ouvrages est invalide") from exc
    else:
        parsed_opening_ids = [opening.id for opening in mission.openings]
    _validate_technical_coverage(mission, parsed_opening_ids)

    directory = os.path.join("uploads", "mmg", "technical-dossiers", str(dossier.id))
    file_path = await uploads.save_upload_file(
        file,
        directory,
        extra_extensions={
            ".txt",
            ".xml",
            ".csv",
            ".json",
            ".zip",
            ".dat",
            ".cut",
            ".dxf",
        },
        prefix=f"v{len(dossier.versions) + 1}_",
    )
    with open(file_path, "rb") as saved_file:
        checksum = hashlib.sha256(saved_file.read()).hexdigest()
    latest = _latest_technical_version(dossier)
    if latest and latest.checksum_sha256 == checksum:
        os.remove(file_path)
        raise HTTPException(409, "Ce fichier est identique à la dernière version")

    analysis = analyze_technical_document(
        Path(file_path),
        normalized_type,
        normalized_source,
        source_reference,
    )
    resolved_source = (
        analysis.detected_source_system
        or normalized_source
        or schemas.TechnicalSourceSystem.OTHER.value
    )
    if is_quoting and resolved_source not in {
        schemas.TechnicalSourceSystem.PROGES.value,
        schemas.TechnicalSourceSystem.ORGADATA.value,
    }:
        os.remove(file_path)
        raise HTTPException(
            422,
            "Format de chiffrage non reconnu. Importez un devis PDF PROGES ou ORGADATA.",
        )
    if is_quoting:
        extracted_quantity = float(analysis.summary.get("total_quantity") or 0)
        expected_quantity = len(parsed_opening_ids)
        if extracted_quantity != expected_quantity:
            analysis.issues.append(
                {
                    "severity": "warning",
                    "code": "commercial_quote_opening_quantity_mismatch",
                    "source": file.filename or "chiffrage",
                    "row": None,
                    "reference": analysis.detected_project_reference,
                    "message": (
                        f"Le chiffrage représente {extracted_quantity:g} ouvrage(s), "
                        f"contre {expected_quantity} dans la mission."
                    ),
                }
            )
            analysis.summary["issue_count"] = len(analysis.issues)
            if analysis.status == "PARSED":
                analysis = analysis.__class__(
                    status="PARSED_WITH_WARNINGS",
                    detected_document_type=analysis.detected_document_type,
                    detected_source_system=analysis.detected_source_system,
                    detected_project_reference=analysis.detected_project_reference,
                    summary=analysis.summary,
                    records=analysis.records,
                    issues=analysis.issues,
                )
    previous_same_type = _latest_technical_version(dossier, normalized_type)
    comparison = (
        compare_material_versions(
            previous_same_type.parsed_records or [],
            analysis.records,
        )
        if normalized_type == schemas.TechnicalDocumentType.CUTTING.value
        and previous_same_type
        else {}
    )
    if is_quoting and previous_same_type:
        comparison = compare_commercial_quote_versions(
            previous_same_type.parsed_records or [],
            analysis.records,
        )
    revision_after_launch = bool(
        normalized_type != schemas.TechnicalDocumentType.QUOTING.value
        and dossier.launched_at
    )
    impact_status = (
        "BLOCKING"
        if revision_after_launch and comparison.get("has_changes")
        else "REVIEW_REQUIRED"
        if comparison.get("has_changes")
        else "NO_CHANGE"
        if previous_same_type
        else "INITIAL"
    )
    revision_status = (
        "PENDING"
        if revision_after_launch and comparison.get("has_changes")
        else "NOT_REQUIRED"
    )
    resolved_external_reference = (
        (source_reference or "").strip()
        or analysis.detected_project_reference
        or None
    )
    external_design_sources = {
        schemas.TechnicalSourceSystem.PROGES.value,
        schemas.TechnicalSourceSystem.ORGADATA.value,
    }
    if (
        dossier.external_source_system
        and resolved_source in external_design_sources
        and dossier.external_source_system in external_design_sources
        and dossier.external_source_system != resolved_source
    ):
        analysis.issues.append(
            {
                "severity": "error",
                "code": "technical_dossier_source_mismatch",
                "source": file.filename or "dossier-technique",
                "row": None,
                "reference": resolved_external_reference,
                "message": (
                    f"Le dossier industriel est rattaché à "
                    f"{dossier.external_source_system}, pas {resolved_source}."
                ),
            }
        )
        analysis.summary["issue_count"] = len(analysis.issues)
    if (
        not dossier.external_source_system
        and resolved_source in external_design_sources
    ):
        dossier.external_source_system = resolved_source
    if not dossier.external_project_reference and resolved_external_reference:
        dossier.external_project_reference = resolved_external_reference
    if (
        dossier.external_project_reference
        and resolved_external_reference
        and dossier.external_project_reference != resolved_external_reference
    ):
        analysis.issues.append(
            {
                "severity": "error",
                "code": "technical_dossier_reference_mismatch",
                "source": file.filename or "dossier-technique",
                "row": None,
                "reference": resolved_external_reference,
                "message": (
                    f"Le dossier industriel attend la référence "
                    f"{dossier.external_project_reference}, pas {resolved_external_reference}."
                ),
            }
        )
        analysis.summary["issue_count"] = len(analysis.issues)
    normalized_analysis_status = (
        "FAILED"
        if any(issue.get("severity") == "error" for issue in analysis.issues)
        else "PARSED_WITH_WARNINGS"
        if analysis.issues and analysis.status == "PARSED"
        else analysis.status
    )
    if normalized_analysis_status != analysis.status:
        analysis = analysis.__class__(
            status=normalized_analysis_status,
            detected_document_type=analysis.detected_document_type,
            detected_source_system=analysis.detected_source_system,
            detected_project_reference=analysis.detected_project_reference,
            summary=analysis.summary,
            records=analysis.records,
            issues=analysis.issues,
        )
    version = models.TechnicalDossierVersion(
        dossier=dossier,
        version_number=len(dossier.versions) + 1,
        document_type=normalized_type,
        source_system=resolved_source,
        source_reference=(
            (source_reference or "").strip()
            or analysis.detected_project_reference
            or None
        ),
        original_filename=file.filename or "dossier-technique",
        stored_filename=os.path.basename(file_path),
        content_type=file.content_type,
        file_path=file_path,
        file_size=os.path.getsize(file_path),
        checksum_sha256=checksum,
        opening_ids=sorted(set(parsed_opening_ids)),
        notes=(notes or "").strip() or None,
        analysis_status=analysis.status,
        detected_document_type=analysis.detected_document_type,
        detected_source_system=analysis.detected_source_system,
        detected_project_reference=analysis.detected_project_reference,
        parsed_summary=analysis.summary,
        parsed_records=analysis.records,
        parsed_issues=analysis.issues,
        analyzed_at=utcnow(),
        previous_version_id=previous_same_type.id if previous_same_type else None,
        comparison_summary=comparison,
        impact_status=impact_status,
        revision_after_launch=revision_after_launch,
        revision_status=revision_status,
        created_by=current_user.get("sub", "Système"),
    )
    db.add(version)
    setattr(dossier, status_field, schemas.TechnicalDossierStatus.DRAFT.value)
    prefix = "quoting" if is_quoting else "production"
    setattr(dossier, f"{prefix}_review_note", None)
    setattr(dossier, f"{prefix}_validated_at", None)
    setattr(dossier, f"{prefix}_validated_by", None)
    if not is_quoting:
        dossier.stock_status = schemas.TechnicalDossierStatus.LOCKED.value
        dossier.stock_review_note = None
        dossier.stock_validated_at = None
        dossier.stock_validated_by = None
        dossier.launch_status = (
            schemas.TechnicalDossierStatus.CORRECTION_REQUIRED.value
            if revision_after_launch
            else schemas.TechnicalDossierStatus.LOCKED.value
        )
        dossier.launch_review_note = (
            "Nouvelle version technique importée après lancement."
            if revision_after_launch
            else None
        )
        dossier.launch_validated_at = None
        dossier.launch_validated_by = None
    db.commit()
    db.refresh(dossier)
    return dossier


@router.get("/missions/{mission_id}/technical-dossier/handoff")
def export_measure_technical_handoff(
    mission_id: int,
    target_system: schemas.TechnicalSourceSystem = schemas.TechnicalSourceSystem.PROGES,
    db: Session = Depends(get_db),
):
    mission = _get_mission_or_404(db, mission_id)
    if mission.status not in {
        models.MeasureMissionStatus.VALIDATED.value,
        models.MeasureMissionStatus.QUOTED.value,
    }:
        raise HTTPException(409, "Validez d'abord le métré et ses ouvrages")
    if not mission.technical_dossier:
        raise HTTPException(404, "Dossier technique introuvable")
    if not mission.openings:
        raise HTTPException(422, "Aucun ouvrage à transmettre")
    from ..services.mmg_to_proges import generate_measure_mission_handoff

    content = generate_measure_mission_handoff(mission, target_system.value)
    filename = (
        f"{mission.technical_dossier.reference}-"
        f"{target_system.value.lower()}-transfert.csv"
    )
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch(
    "/missions/{mission_id}/technical-dossier/submit",
    response_model=schemas.TechnicalDossierResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def submit_measure_technical_dossier(
    mission_id: int,
    phase: schemas.TechnicalDocumentType,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    _assert_technical_edit(db, current_user)
    mission = _get_mission_or_404(db, mission_id)
    dossier = mission.technical_dossier
    if not dossier:
        raise HTTPException(404, "Dossier technique introuvable")
    dossier = (
        db.query(models.TechnicalDossier)
        .filter(models.TechnicalDossier.id == dossier.id)
        .with_for_update()
        .one()
    )
    is_quoting = phase == schemas.TechnicalDocumentType.QUOTING
    if not is_quoting and not _sale_is_signed(mission):
        raise HTTPException(409, "Le devis client doit être signé avant le contrôle fabrication")
    status_field = "quoting_status" if is_quoting else "production_status"
    if getattr(dossier, status_field) not in {
        schemas.TechnicalDossierStatus.DRAFT.value,
        schemas.TechnicalDossierStatus.CORRECTION_REQUIRED.value,
    }:
        raise HTTPException(409, "Ce dossier ne peut pas être soumis dans son état actuel")
    required_types = (
        [schemas.TechnicalDocumentType.QUOTING.value]
        if is_quoting
        else [
            schemas.TechnicalDocumentType.FABRICATION.value,
            schemas.TechnicalDocumentType.CUTTING.value,
        ]
    )
    for required_type in required_types:
        latest = _latest_technical_version(dossier, required_type)
        if not latest:
            label = "chiffrage" if is_quoting else required_type.lower()
            raise HTTPException(422, f"Ajoutez le fichier {label} PROGES/ORGADATA")
        _validate_technical_coverage(mission, latest.opening_ids or [])
    if is_quoting:
        _validate_quoting_document_analysis(dossier)
    else:
        _validate_production_document_analysis(dossier)
    prefix = "quoting" if is_quoting else "production"
    setattr(dossier, status_field, schemas.TechnicalDossierStatus.TO_REVIEW.value)
    setattr(dossier, f"{prefix}_submitted_at", utcnow())
    setattr(dossier, f"{prefix}_submitted_by", current_user.get("sub", "Système"))
    sync_opportunity_from_mission(
        db,
        mission,
        current_user.get("sub", "Système"),
    )
    db.commit()
    db.refresh(dossier)
    return dossier


@router.patch(
    "/missions/{mission_id}/technical-dossier/review",
    response_model=schemas.TechnicalDossierResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def review_measure_technical_dossier(
    mission_id: int,
    item: schemas.TechnicalDossierReviewRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    if not (_current_roles(current_user) & BE_REVIEW_ROLES):
        raise HTTPException(403, "La validation du dossier technique est réservée au BE")
    mission = _get_mission_or_404(db, mission_id)
    dossier = mission.technical_dossier
    if not dossier:
        raise HTTPException(404, "Dossier technique introuvable")
    is_quoting = item.phase == schemas.TechnicalDocumentType.QUOTING
    status_field = "quoting_status" if is_quoting else "production_status"
    prefix = "quoting" if is_quoting else "production"
    if getattr(dossier, status_field) != schemas.TechnicalDossierStatus.TO_REVIEW.value:
        raise HTTPException(409, "Cette phase n'est pas en attente de contrôle")
    actor = current_user.get("sub", "Système")
    note = (item.note or "").strip() or None
    if item.action == schemas.TechnicalDossierReviewAction.REQUEST_CORRECTION:
        if not note:
            raise HTTPException(422, "Précisez la correction attendue")
        setattr(dossier, status_field, schemas.TechnicalDossierStatus.CORRECTION_REQUIRED.value)
        setattr(dossier, f"{prefix}_review_note", note)
        setattr(dossier, f"{prefix}_validated_at", None)
        setattr(dossier, f"{prefix}_validated_by", None)
    else:
        required_types = (
            [schemas.TechnicalDocumentType.QUOTING.value]
            if is_quoting
            else [
                schemas.TechnicalDocumentType.FABRICATION.value,
                schemas.TechnicalDocumentType.CUTTING.value,
            ]
        )
        for required_type in required_types:
            latest = _latest_technical_version(dossier, required_type)
            if not latest:
                raise HTTPException(422, f"Fichier {required_type.lower()} absent")
            _validate_technical_coverage(mission, latest.opening_ids or [])
        cutting = None
        if is_quoting:
            _validate_quoting_document_analysis(dossier)
        else:
            cutting = _validate_production_document_analysis(dossier)
        setattr(dossier, status_field, schemas.TechnicalDossierStatus.VALIDATED.value)
        setattr(dossier, f"{prefix}_review_note", note)
        setattr(dossier, f"{prefix}_validated_at", utcnow())
        setattr(dossier, f"{prefix}_validated_by", actor)
        if cutting:
            dossier.stock_status = schemas.TechnicalDossierStatus.TO_REVIEW.value
            dossier.stock_review_note = None
            dossier.stock_validated_at = None
            dossier.stock_validated_by = None
            dossier.launch_status = schemas.TechnicalDossierStatus.LOCKED.value
            dossier.launch_review_note = None
            dossier.launch_validated_at = None
            dossier.launch_validated_by = None
    sync_opportunity_from_mission(db, mission, actor)
    db.commit()
    db.refresh(dossier)
    return dossier


@router.get("/missions/{mission_id}/technical-dossier/governance")
def get_measure_technical_governance(
    mission_id: int,
    db: Session = Depends(get_db),
):
    mission = _get_mission_or_404(db, mission_id)
    return _technical_governance_payload(db, mission)


@router.post(
    "/missions/{mission_id}/technical-dossier/reservation",
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def reserve_measure_technical_cutting(
    mission_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    """Réserve directement le dernier débit approuvé, sans second téléversement."""
    security.assert_permission(db, current_user, "workshop.reserve_stock")
    mission = _get_mission_or_404(db, mission_id)
    dossier = mission.technical_dossier
    if not dossier:
        raise HTTPException(404, "Dossier technique introuvable")
    dossier = (
        db.query(models.TechnicalDossier)
        .filter(models.TechnicalDossier.id == dossier.id)
        .with_for_update()
        .one()
    )
    if not mission.sale_order_id or not mission.sale_order:
        raise HTTPException(409, "Le dossier technique doit être lié à un devis signé")
    if dossier.production_status != schemas.TechnicalDossierStatus.VALIDATED.value:
        raise HTTPException(409, "Le BE doit valider fabrication et débit avant la réservation")
    if dossier.stock_status != schemas.TechnicalDossierStatus.VALIDATED.value:
        raise HTTPException(409, "Le stock doit être validé avant la réservation atelier")

    cutting = _validate_production_document_analysis(dossier)
    source_label = f"technical_dossier:{dossier.id}:cutting_version:{cutting.id}"
    same_version = (
        db.query(models.StockReservation)
        .filter(
            models.StockReservation.technical_dossier_version_id == cutting.id,
        )
        .order_by(models.StockReservation.created_at.desc())
        .first()
    )
    if same_version:
        if same_version.status == "reserved":
            return _technical_governance_payload(db, mission)
        if same_version.status == "cancelled":
            try:
                reactivate_cancelled_reservation(db, same_version)
                if mission.sale_order.status in {"VALIDATED", "IN_DESIGN"}:
                    mission.sale_order.status = "READY_FOR_PROD"
                db.commit()
                fresh_mission = _get_mission_or_404(db, mission_id)
                return _technical_governance_payload(db, fresh_mission)
            except ValueError as exc:
                db.rollback()
                raise HTTPException(409, str(exc)) from exc
        raise HTTPException(
            409,
            f"La version de débit validée a déjà une réservation {same_version.status} "
            f"({same_version.reference}); elle ne peut pas être réservée une seconde fois.",
        )
    consumed_previous_version = (
        db.query(models.StockReservation)
        .join(
            models.TechnicalDossierVersion,
            models.TechnicalDossierVersion.id
            == models.StockReservation.technical_dossier_version_id,
        )
        .filter(
            models.TechnicalDossierVersion.dossier_id == dossier.id,
            models.StockReservation.status == "consumed",
        )
        .first()
    )
    if consumed_previous_version:
        raise HTTPException(
            409,
            "Une version antérieure de ce dossier a déjà été consommée. "
            "La nouvelle version doit faire l'objet d'une régularisation de stock "
            "contrôlée; une réservation du total complet est interdite.",
        )
    active_other_version = (
        db.query(models.StockReservation)
        .filter(
            models.StockReservation.sale_order_id == mission.sale_order_id,
            models.StockReservation.status == "reserved",
            models.StockReservation.source_label.notin_(["devis libre", "devis_libre"]),
        )
        .first()
    )
    if active_other_version:
        raise HTTPException(
            409,
            "Une réservation active issue d'une autre version de débit existe déjà. "
            "Annulez-la avant de réserver la version validée.",
        )

    trace_note = (
        f"Dossier {dossier.reference} | CUTTING v{cutting.version_number} "
        f"(id={cutting.id}, sha256={cutting.checksum_sha256})"
    )
    try:
        create_reservation(
            db,
            _records_from_technical_version(cutting),
            source_label=source_label,
            created_by=current_user.get("sub", "Système"),
            source_location="WH/Stock",
            order_reference=mission.sale_order.reference,
            sale_order_id=mission.sale_order_id,
            notes=trace_note,
            technical_cutting_version_id=cutting.id,
        )
        if mission.sale_order.status in {"VALIDATED", "IN_DESIGN"}:
            mission.sale_order.status = "READY_FOR_PROD"
        db.commit()
        db.refresh(dossier)
        return _technical_governance_payload(db, mission)
    except IntegrityError as exc:
        db.rollback()
        concurrent = (
            db.query(models.StockReservation)
            .filter(
                models.StockReservation.technical_dossier_version_id == cutting.id
            )
            .first()
        )
        if concurrent and concurrent.status == "reserved":
            fresh_mission = _get_mission_or_404(db, mission_id)
            return _technical_governance_payload(db, fresh_mission)
        raise HTTPException(
            409,
            "Cette version de débit possède déjà une réservation.",
        ) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc


@router.patch(
    "/missions/{mission_id}/technical-dossier/gate-review",
    response_model=schemas.TechnicalDossierResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def review_measure_technical_gate(
    mission_id: int,
    item: schemas.TechnicalGateReviewRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    mission = _get_mission_or_404(db, mission_id)
    dossier = mission.technical_dossier
    if not dossier:
        raise HTTPException(404, "Dossier technique introuvable")
    roles = _current_roles(current_user)
    actor = current_user.get("sub", "Système")
    note = (item.note or "").strip() or None

    if item.gate == schemas.TechnicalGate.STOCK:
        if not (roles & STOCK_REVIEW_ROLES):
            raise HTTPException(403, "La validation stock est réservée au chef stock")
        if dossier.production_status != schemas.TechnicalDossierStatus.VALIDATED.value:
            raise HTTPException(409, "Le BE doit valider fabrication et débit avant le stock")
        if item.action == schemas.TechnicalDossierReviewAction.REQUEST_CORRECTION:
            if not note:
                raise HTTPException(422, "Précisez la correction stock attendue")
            dossier.stock_status = schemas.TechnicalDossierStatus.CORRECTION_REQUIRED.value
            dossier.stock_review_note = note
            dossier.stock_validated_at = None
            dossier.stock_validated_by = None
        else:
            matrix = build_document_matrix(dossier.versions)
            if not matrix["complete"] or not matrix["reference_consistent"]:
                raise HTTPException(409, "La matrice documentaire est incomplète ou incohérente")
            cutting = _validate_production_document_analysis(dossier)
            if cutting.revision_status == "PENDING":
                raise HTTPException(409, "La révision post-lancement doit d'abord être approuvée")
            stock = _technical_stock_snapshot(db, dossier)
            if not stock["ready"]:
                raise HTTPException(
                    409,
                    f"Stock non validable : {stock['unknown_count']} inconnue(s), "
                    f"{stock['shortage_count']} manque(s).",
                )
            dossier.stock_status = schemas.TechnicalDossierStatus.VALIDATED.value
            dossier.stock_review_note = note
            dossier.stock_validated_at = utcnow()
            dossier.stock_validated_by = actor
            dossier.launch_status = schemas.TechnicalDossierStatus.TO_REVIEW.value
            cutting.stock_data_approved_at = utcnow()
            cutting.stock_data_approved_by = actor
    else:
        if not (roles & LAUNCH_REVIEW_ROLES):
            raise HTTPException(403, "Le lancement est réservé au chef d'atelier")
        if dossier.stock_status != schemas.TechnicalDossierStatus.VALIDATED.value:
            raise HTTPException(409, "Le stock doit être validé avant le lancement atelier")
        if item.action == schemas.TechnicalDossierReviewAction.REQUEST_CORRECTION:
            if not note:
                raise HTTPException(422, "Précisez le blocage atelier")
            dossier.launch_status = schemas.TechnicalDossierStatus.CORRECTION_REQUIRED.value
            dossier.launch_review_note = note
            dossier.launch_validated_at = None
            dossier.launch_validated_by = None
        else:
            execution = _technical_execution_context(db, mission)
            cutting = _validate_production_document_analysis(dossier)
            reservation = execution["reservation"]
            consumed_material_already_matches = (
                reservation
                and reservation["status"] == "consumed"
                and reservation["technical_dossier_version_id"] != cutting.id
                and _consumed_reservation_matches_cutting(
                    db.query(models.StockReservation)
                    .filter(models.StockReservation.id == reservation["id"])
                    .first(),
                    cutting,
                )
                and execution["preparation"]
                and execution["preparation"]["status"] == "consumed"
            )
            if (
                not reservation
                or (
                    not consumed_material_already_matches
                    and (
                        reservation["status"] != "reserved"
                        or reservation["technical_dossier_version_id"] != cutting.id
                    )
                )
            ):
                raise HTTPException(
                    409,
                    "Créez une réservation active depuis la dernière version de débit "
                    "validée avant d'autoriser le lancement.",
                )
            dossier.launch_status = schemas.TechnicalDossierStatus.VALIDATED.value
            dossier.launch_review_note = note
            dossier.launch_validated_at = utcnow()
            dossier.launch_validated_by = actor

    db.commit()
    db.refresh(dossier)
    return dossier


@router.patch(
    "/missions/{mission_id}/technical-dossier/versions/{version_id}/revision-review",
    response_model=schemas.TechnicalDossierResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def review_measure_technical_revision(
    mission_id: int,
    version_id: int,
    item: schemas.TechnicalRevisionReviewRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    if not (_current_roles(current_user) & BE_REVIEW_ROLES):
        raise HTTPException(403, "La revue de révision est réservée au BE")
    mission = _get_mission_or_404(db, mission_id)
    dossier = mission.technical_dossier
    if not dossier:
        raise HTTPException(404, "Dossier technique introuvable")
    version = next((value for value in dossier.versions if value.id == version_id), None)
    if not version:
        raise HTTPException(404, "Version technique introuvable")
    if version.revision_status != "PENDING":
        raise HTTPException(409, "Cette version n'attend pas de décision de révision")
    note = (item.note or "").strip() or None
    if item.action == schemas.TechnicalDossierReviewAction.REQUEST_CORRECTION and not note:
        raise HTTPException(422, "Précisez la correction demandée")
    version.revision_status = (
        "APPROVED"
        if item.action == schemas.TechnicalDossierReviewAction.VALIDATE
        else "CORRECTION_REQUIRED"
    )
    version.revision_review_note = note
    version.revision_reviewed_at = utcnow()
    version.revision_reviewed_by = current_user.get("sub", "Système")
    db.commit()
    db.refresh(dossier)
    return dossier


@router.get(
    "/missions/{mission_id}/technical-dossier/versions/{version_id}/download",
)
def download_measure_technical_version(
    mission_id: int,
    version_id: int,
    db: Session = Depends(get_db),
):
    mission = _get_mission_or_404(db, mission_id)
    if not mission.technical_dossier:
        raise HTTPException(404, "Dossier technique introuvable")
    version = (
        db.query(models.TechnicalDossierVersion)
        .filter(
            models.TechnicalDossierVersion.id == version_id,
            models.TechnicalDossierVersion.dossier_id == mission.technical_dossier.id,
        )
        .first()
    )
    if not version:
        raise HTTPException(404, "Version technique introuvable")
    if not os.path.exists(version.file_path):
        raise HTTPException(404, "Fichier technique introuvable sur le stockage")
    return FileResponse(
        version.file_path,
        media_type=version.content_type or "application/octet-stream",
        filename=version.original_filename,
    )


@router.patch(
    "/missions/{mission_id}/verification",
    response_model=schemas.MeasureMissionResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def update_measure_mission_verification(
    mission_id: int,
    item: schemas.MeasureVerificationUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    mission = _get_mission_or_404(db, mission_id)
    if mission.status != models.MeasureMissionStatus.VALIDATED.value:
        raise HTTPException(409, "Le contrôle BE doit être validé avant cette confirmation")
    actor = current_user.get("sub", "Système")
    if item.action == schemas.MeasureVerificationAction.CLIENT_APPROVED:
        if mission.source_type == schemas.MeasureSourceType.SITE_VISIT.value:
            raise HTTPException(409, "Les cotes ont déjà été relevées et vérifiées par MMG")
        mission.client_approved_at = utcnow()
        mission.client_approved_by = actor
        if mission.project_scope == schemas.MeasureProjectScope.SUPPLY_ONLY.value:
            mission.verification_status = schemas.MeasureVerificationStatus.READY_FOR_FABRICATION.value
        else:
            mission.verification_status = schemas.MeasureVerificationStatus.SITE_VERIFICATION_REQUIRED.value
    else:
        if not (_current_roles(current_user) & BE_REVIEW_ROLES):
            raise HTTPException(403, "La vérification chantier est réservée aux profils habilités")
        if not mission.site_address_id:
            raise HTTPException(422, "Renseignez l'adresse du chantier avant de confirmer la vérification")
        mission.site_verified_at = utcnow()
        mission.site_verified_by = actor
        mission.verification_status = schemas.MeasureVerificationStatus.READY_FOR_FABRICATION.value
    db.commit()
    db.refresh(mission)
    return _serialize_mission(mission)


@router.post(
    "/missions/{mission_id}/generate-quote",
    response_model=schemas.MeasureMissionQuoteResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def generate_measure_mission_quote(
    mission_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    mission = _get_mission_or_404(db, mission_id)
    if mission.status not in {
        models.MeasureMissionStatus.VALIDATED.value,
        models.MeasureMissionStatus.QUOTED.value,
    }:
        raise HTTPException(409, "Le contrôle BE doit être validé avant le chiffrage")
    if (
        mission.verification_status
        != schemas.MeasureVerificationStatus.READY_FOR_FABRICATION.value
    ):
        raise HTTPException(
            409,
            "La responsabilité des cotes doit être confirmée avant de générer le devis",
        )
    if not mission.openings:
        raise HTTPException(422, "Aucun ouvrage validé à chiffrer")
    if (
        not mission.technical_dossier
        or mission.technical_dossier.quoting_status
        != schemas.TechnicalDossierStatus.VALIDATED.value
    ):
        raise HTTPException(
            409,
            "Le chiffrage PROGES/ORGADATA doit être validé par le BE avant de créer la proposition",
        )
    invalid_openings = [
        opening
        for opening in mission.openings
        if opening.status != schemas.MeasureOpeningStatus.VALIDATED.value
    ]
    if invalid_openings:
        raise HTTPException(422, "Tous les ouvrages doivent être validés par le BE")
    quoting_version = _validate_quoting_document_analysis(mission.technical_dossier)

    if mission.sale_order_id:
        sale = (
            db.query(models.SaleOrder)
            .filter(models.SaleOrder.id == mission.sale_order_id)
            .first()
        )
        if sale:
            return schemas.MeasureMissionQuoteResponse(
                mission_id=mission.id,
                sale_order_id=sale.id,
                sale_reference=sale.reference,
                created=False,
                line_count=len(sale.lines),
            )

    site_label = (
        f"{mission.site.reference} - {mission.site.formatted_address}"
        if mission.site
        else "chantier à préciser"
    )
    quote_summary = quoting_version.parsed_summary or {}
    effective_discount_pct = round(
        float(quote_summary.get("effective_discount_pct") or 0),
        6,
    )
    source_reference = (
        quoting_version.detected_project_reference
        or quoting_version.source_reference
        or mission.technical_dossier.reference
    )
    sale = models.SaleOrder(
        reference=next_number(db, "quote"),
        client_name=mission.client.name,
        client_contact=mission.client.phone or mission.client.contact_name,
        client_email=mission.client.email,
        client_address=mission.client.address,
        status="DRAFT",
        workflow_type="FABRICATION_FROM_MEASURE",
        tax_rate=float(quote_summary.get("tax_rate") or 20),
        notes=(
            f"Proposition générée depuis le chiffrage "
            f"{quoting_version.source_system} {source_reference}, "
            f"version V{quoting_version.version_number}, mission {mission.reference}, "
            f"{site_label}. Contrôle commercial requis avant envoi."
        ),
        author=current_user.get("sub", "Système"),
    )
    db.add(sale)
    db.flush()

    for record in quoting_version.parsed_records or []:
        description = " - ".join(
            part
            for part in [
                str(record.get("position") or "").strip(),
                str(record.get("description") or "").strip(),
            ]
            if part
        )
        sale.lines.append(
            models.SaleOrderLine(
                line_type="SERVICE",
                description=description[:500],
                quantity=float(record.get("quantity") or 0),
                unit_price=float(record.get("unit_price") or 0),
                discount_pct=effective_discount_pct,
                visual_config=None,
            )
        )
    db.flush()
    mission.sale_order_id = sale.id
    mission.status = models.MeasureMissionStatus.QUOTED.value
    if mission.opportunity:
        mission.opportunity.sale_order_id = sale.id
        mission.opportunity.estimated_amount = float(
            quote_summary.get("subtotal_after_discount") or 0
        )
        db.flush()
        sync_opportunity_from_sale(
            db,
            sale,
            current_user.get("sub", "Système"),
        )
    db.commit()
    db.refresh(sale)
    return schemas.MeasureMissionQuoteResponse(
        mission_id=mission.id,
        sale_order_id=sale.id,
        sale_reference=sale.reference,
        created=True,
        line_count=len(sale.lines),
    )


@router.post(
    "/missions/{mission_id}/documents",
    response_model=schemas.MeasureMissionResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
async def upload_measure_mission_document(
    mission_id: int,
    file: UploadFile = File(...),
    opening_id: Optional[int] = None,
    document_type: str = "SOURCE_MEASURE",
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    mission = _get_mission_or_404(db, mission_id)
    _ensure_mission_editable(mission)
    opening = None
    if opening_id is not None:
        opening = (
            db.query(models.MeasureOpening)
            .filter(
                models.MeasureOpening.id == opening_id,
                models.MeasureOpening.mission_id == mission.id,
            )
            .first()
        )
        if not opening:
            raise HTTPException(404, "Ouvrage introuvable pour cette mission")
    file_path = await uploads.save_upload_file(
        file,
        os.path.join("uploads", "measure_missions", str(mission.id)),
        extra_extensions={".txt"},
        prefix=f"metre_{mission.id}_",
    )
    document = models.MeasureMissionDocument(
        mission_id=mission.id,
        opening_id=opening.id if opening else None,
        original_filename=os.path.basename(file.filename or "document"),
        stored_filename=os.path.basename(file_path),
        content_type=file.content_type,
        file_path=file_path.replace(os.sep, "/"),
        file_size=os.path.getsize(file_path),
        document_type=document_type[:50] or "SOURCE_MEASURE",
        uploaded_by=current_user.get("sub", "Système"),
    )
    db.add(document)
    db.commit()
    db.refresh(mission)
    return _serialize_mission(mission)


@router.get("/missions/{mission_id}/documents/{document_id}/download")
def download_measure_mission_document(
    mission_id: int,
    document_id: int,
    db: Session = Depends(get_db),
):
    document = (
        db.query(models.MeasureMissionDocument)
        .filter(
            models.MeasureMissionDocument.id == document_id,
            models.MeasureMissionDocument.mission_id == mission_id,
        )
        .first()
    )
    if not document:
        raise HTTPException(404, "Document de cotes introuvable")
    if not os.path.exists(document.file_path):
        raise HTTPException(404, "Fichier source introuvable")
    filename = document.original_filename.replace('"', "")
    return FileResponse(
        document.file_path,
        media_type=document.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete(
    "/missions/{mission_id}/documents/{document_id}",
    response_model=schemas.MeasureMissionResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def delete_measure_mission_document(
    mission_id: int,
    document_id: int,
    db: Session = Depends(get_db),
):
    mission = _get_mission_or_404(db, mission_id)
    _ensure_mission_editable(mission)
    document = (
        db.query(models.MeasureMissionDocument)
        .filter(
            models.MeasureMissionDocument.id == document_id,
            models.MeasureMissionDocument.mission_id == mission_id,
        )
        .first()
    )
    if not document:
        raise HTTPException(404, "Document de cotes introuvable")
    file_path = document.file_path
    db.delete(document)
    db.commit()
    if os.path.exists(file_path):
        os.remove(file_path)
    db.refresh(mission)
    return _serialize_mission(mission)

@router.post(
    "/",
    response_model=schemas.MMGResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
async def create_dossier(
    item: schemas.MMGCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    # 1. Generate Reference
    ref = generate_reference(db)

    mission = None
    if item.measure_mission_id:
        mission = (
            db.query(models.MeasureMission)
            .filter(models.MeasureMission.id == item.measure_mission_id)
            .first()
        )
        if not mission:
            raise HTTPException(404, "Mission de métré introuvable")
    effective_client_id = item.client_id or (mission.client_id if mission else None)
    client = None
    if effective_client_id:
        client = db.query(models.Client).filter(models.Client.id == effective_client_id).first()
        if not client:
            raise HTTPException(404, "Client introuvable")
    if mission and item.client_id and mission.client_id != item.client_id:
        raise HTTPException(400, "La mission et le dossier ne concernent pas le même client")

    site = mission.site if mission and mission.site else None
    if effective_client_id and not site:
        site = _resolve_site(db, effective_client_id, item.site_address_id, item.site)

    if effective_client_id and not mission:
        mission = models.MeasureMission(
            reference=next_number(db, "measure_mission"),
            client_id=effective_client_id,
            site_address_id=site.id if site else None,
            sale_order_id=item.sale_order_id,
            status=models.MeasureMissionStatus.TO_REVIEW.value,
            source_type=schemas.MeasureSourceType.AGENCY_ASSISTED.value,
            project_scope=schemas.MeasureProjectScope.SUPPLY_AND_INSTALL.value,
            verification_status=schemas.MeasureVerificationStatus.UNVERIFIED.value,
            purpose="Prise de côte saisie directement",
            created_by=current_user.get("sub", "Système"),
        )
        db.add(mission)
        db.flush()
    elif mission and mission.status not in {
        models.MeasureMissionStatus.VALIDATED.value,
        models.MeasureMissionStatus.QUOTED.value,
        models.MeasureMissionStatus.CANCELLED.value,
    }:
        mission.status = models.MeasureMissionStatus.TO_REVIEW.value
    
    # 2. Save Signature
    sig_path = save_base64_image(item.signature, "signatures", "sig")
    
    # 3. Save Photos (assume they might be base64 if list of strings)
    photo_paths = []
    for i, p_base64 in enumerate(item.photos):
        path = save_base64_image(p_base64, "photos", f"photo_{i}")
        if path:
            photo_paths.append(path)
    
    # 4. Create Model
    # Configuration fine persistée telle quelle (JSON) : forme, ventilation,
    # soubassement... + sous-clé "annexes" (volets, moustiquaire, pose...).
    # C'est la source des plus-values calculées par send-quote.
    stored_configuration = item.configuration.model_dump()
    stored_configuration["annexes"] = item.annexes.model_dump() if item.annexes else {}

    client_name = client.name if client else item.client.name
    client_contact = (client.phone or client.contact_name or "") if client else item.client.contact
    client_address = (client.address or "") if client else item.client.address
    client_email = (client.email or "") if client else item.client.email
    client_type = item.client.client_type or (client.customer_type if client else "PARTICULIER")
    site_address = _site_address_text(site) if site else item.client.site_address

    db_item = models.MMG(
        reference=ref,
        client_id=effective_client_id,
        site_address_id=site.id if site else None,
        measure_mission_id=mission.id if mission else None,
        client_name=client_name,
        client_contact=client_contact,
        client_address=client_address,
        site_address=site_address,
        client_email=client_email,
        client_type=client_type,
        
        width=item.measurements.width_mm,
        height=item.measurements.height_mm,
        passage_height=item.measurements.passage_height_mm,
        
        sill_height=item.options.sill_height_mm,
        transom_height=item.options.transom_height_mm,
        shutter_type=item.options.shutter_type,
        
        view_type=item.configuration.view,
        opening_type=item.configuration.opening_type,
        opening_side=item.configuration.opening_side,
        sash_count=item.configuration.sash_count,
        
        material=item.configuration.material,
        product_series=item.configuration.product_series,
        color_ral=item.configuration.color_ral,
        is_bicolor=item.configuration.is_bicolor,
        texture=item.configuration.texture,
        glazing_type=item.configuration.glazing_type,
        installation_type=item.configuration.installation_type,
        hardware_type=item.configuration.hardware_type,
        is_pmr_compliant=item.configuration.is_pmr_compliant,
        doublage_thickness=item.configuration.doublage_thickness,
        keep_existing_frame=item.configuration.keep_existing_frame,
        
        floor_number=item.logistics.floor_number if item.logistics else 0,
        access_difficulty=item.logistics.access_difficulty if item.logistics else "Standard",
        environment=item.logistics.environment if item.logistics else "Standard",
        
        photos=",".join(photo_paths),
        signature=sig_path,
        configuration=stored_configuration,
        status=models.MMGStatus.SENT,
        sale_order_id=item.sale_order_id
    )
    
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    
    return db_item

@router.post(
    "/from-sale/{sale_id}",
    response_model=schemas.MMGResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def create_from_sale(
    sale_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    sale = db.query(models.SaleOrder).filter(models.SaleOrder.id == sale_id).first()
    if not sale:
        raise HTTPException(404, "Devis introuvable")

    client_filters = [models.Client.name == sale.client_name]
    if sale.client_email:
        client_filters.append(models.Client.email == sale.client_email)
    if sale.client_contact:
        client_filters.append(models.Client.phone == sale.client_contact)
    crm_client = db.query(models.Client).filter(or_(*client_filters)).first()
    if not crm_client:
        crm_client = models.Client(
            name=sale.client_name,
            email=sale.client_email,
            phone=sale.client_contact,
            address=sale.client_address,
            customer_type="B2C",
            is_active=True,
        )
        db.add(crm_client)
        db.flush()

    site = None
    if sale.client_address:
        site = _resolve_site(
            db,
            crm_client.id,
            site_data=schemas.ClientSiteAddressCreate(
                client_id=crm_client.id,
                label="Chantier du devis",
                address_line1=sale.client_address,
                country=crm_client.country or "FR",
                is_default=True,
            ),
        )

    mission = models.MeasureMission(
        reference=next_number(db, "measure_mission"),
        client_id=crm_client.id,
        site_address_id=site.id if site else None,
        sale_order_id=sale.id,
        status=models.MeasureMissionStatus.TO_SCHEDULE.value,
        purpose=f"Métré fabrication pour {sale.reference}",
        created_by=current_user.get("sub", "Système"),
    )
    db.add(mission)
    db.flush()

    ref = generate_reference(db)
    sale.workflow_type = "FABRICATION_ESTIMATE"
    
    db_item = models.MMG(
        reference=ref,
        client_id=crm_client.id,
        site_address_id=site.id if site else None,
        measure_mission_id=mission.id,
        client_name=sale.client_name,
        client_contact=sale.client_contact,
        client_address=sale.client_address,
        site_address=_site_address_text(site) if site else sale.client_address,
        client_email=sale.client_email,
        sale_order_id=sale.id,
        status=models.MMGStatus.SENT, # En attente de métré
        
        # Default empty/standard values
        width=0, height=0, passage_height=0,
        view_type="interior", opening_type="tirant", opening_side="gauche",
        sash_count=1, material="ALU", product_series="Standard"
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

@router.get("/", response_model=List[schemas.MMGDetail])
def list_dossiers(db: Session = Depends(get_db)):
    dossiers = db.query(models.MMG).order_by(models.MMG.created_at.desc()).all()
    return [_serialize_detail(d) for d in dossiers]

@router.get("/{dossier_id}", response_model=schemas.MMGDetail)
def get_dossier(dossier_id: int, db: Session = Depends(get_db)):
    db_item = db.query(models.MMG).filter(models.MMG.id == dossier_id).first()
    if not db_item:
        raise HTTPException(404, "Dossier not found")

    return _serialize_detail(db_item)

@router.patch(
    "/{dossier_id}/status",
    response_model=schemas.MMGResponse,
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def update_status(dossier_id: int, update: schemas.MMGStatusUpdate, db: Session = Depends(get_db)):
    db_item = db.query(models.MMG).filter(models.MMG.id == dossier_id).first()
    if not db_item:
        raise HTTPException(404, "Dossier not found")
    
    previous_status = db_item.status
    db_item.status = update.status
    
    # Trigger Proges Export if validated
    if update.status == models.MMGStatus.VALIDATED and previous_status != models.MMGStatus.VALIDATED:
        from ..services import mmg_to_proges
        mmg_to_proges.save_proges_export({
            "reference": db_item.reference,
            "width": db_item.width,
            "height": db_item.height,
            "opening_type": db_item.opening_type,
            "sash_count": db_item.sash_count,
            "material": db_item.material,
            "color_ral": db_item.color_ral,
            "glazing_type": db_item.glazing_type,
            "installation_type": db_item.installation_type,
            "client_type": db_item.client_type
        })
        
    db.commit()
    db.refresh(db_item)
    return db_item

@router.post(
    "/{dossier_id}/send-quote",
    dependencies=CRM_EDIT_DEPENDENCIES,
)
def send_quote(dossier_id: int, db: Session = Depends(get_db)):
    db_item = db.query(models.MMG).filter(models.MMG.id == dossier_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="MMG Dossier not found")
    
    # Create SaleOrder if it doesn't exist
    existing_sale = db.query(models.SaleOrder).filter(models.SaleOrder.client_name == db_item.client_name, models.SaleOrder.notes.contains(db_item.reference)).first()
    
    if not existing_sale:
        # Même séquence transactionnelle que les devis /v2/sales (DEV-YYYY-XXXX)
        ref = next_number(db, "quote")
        
        sale = models.SaleOrder(
            reference=ref,
            client_name=db_item.client_name,
            client_contact=db_item.client_contact,
            client_email=db_item.client_email,
            client_address=db_item.client_address,
            workflow_type="FABRICATION_FROM_MEASURE",
            status="SENT",
            notes=f"Devis généré automatiquement depuis le dossier technique {db_item.reference}.",
            author="Système (Auto)"
        )
        db.add(sale)
        db.flush()
        
        # Estimate a price based on dimensions (Mock Logic)
        surface_m2 = (db_item.width / 1000) * (db_item.height / 1000)
        base_price_per_m2 = 450 if db_item.material == "ALU" else 250
        estimated_price = surface_m2 * base_price_per_m2
        
        line_desc = f"{db_item.material} - {db_item.product_series} ({db_item.width}x{db_item.height}mm)"
        if db_item.installation_type:
            line_desc += f" (Pose: {db_item.installation_type})"
            
        sale_line = models.SaleOrderLine(
            order_id=sale.id,
            description=line_desc,
            quantity=1.0,
            unit_price=round(estimated_price, 2)
        )
        db.add(sale_line)
        
        # 0. Forme Spéciale (Plus-value)
        # La configuration fine persistée à la création (colonne JSON
        # `configuration`) alimente les règles de plus-values ci-dessous.
        # Rétrocompat : les dossiers créés avant cette colonne retombent
        # sur {} et ne déclenchent aucune plus-value.
        config = db_item.configuration or {}
        shape = config.get("shape", "Rectangulaire")
        if shape != "Rectangulaire":
            shape_markup = 0.40 if shape == "Cintré" else 0.20
            shape_price = estimated_price * shape_markup
            db.add(models.SaleOrderLine(
                order_id=sale.id,
                description=f"Plus-value Forme : {shape}",
                quantity=1.0,
                unit_price=round(shape_price, 2)
            ))
            
        # Tapées d'isolation (Pose à neuf)
        if db_item.installation_type == "Neuf":
            perimeter_m = (db_item.width + db_item.height) * 2 / 1000
            db.add(models.SaleOrderLine(
                order_id=sale.id,
                description=f"Tapées d'isolation ({config.get('doublage_thickness', '100')}mm)",
                quantity=round(perimeter_m, 2),
                unit_price=15.0 # 15€ per linear meter
            ))
            
        # Grille de Ventilation
        ventilation = config.get("ventilation", "Aucune")
        if ventilation != "Aucune":
            vent_price = 45.0 if ventilation == "Acoustique" else 25.0
            db.add(models.SaleOrderLine(
                order_id=sale.id,
                description=f"Accessoire : Grille de Ventilation {ventilation}",
                quantity=1.0,
                unit_price=vent_price
            ))
            
        # Soubassement Plein
        soubassement_type = config.get("soubassement_type", "Vitré")
        if soubassement_type == "Plein":
            db.add(models.SaleOrderLine(
                order_id=sale.id,
                description="Option : Panneau de Soubassement Plein isolant",
                quantity=1.0,
                unit_price=65.0 # Forfaitaire
            ))
        
        # Add Annexes & Options
        annexes = config.get("annexes", {})
        
        # 1. Volet Roulant / Battant
        vr_type = annexes.get("volet_roulant", "Aucun")
        vb_type = annexes.get("volet_battant", "Aucun")
        
        if vr_type != "Aucun":
            vr_price = 150 if vr_type == "Manuel" else (280 if vr_type == "Electrique" else 450)
            db.add(models.SaleOrderLine(
                order_id=sale.id,
                description=f"Option : Volet Roulant {vr_type}",
                quantity=1.0,
                unit_price=vr_price
            ))
        elif vb_type != "Aucun":
            vb_price = 120 if vb_type == "1 Vantail" else 200
            db.add(models.SaleOrderLine(
                order_id=sale.id,
                description=f"Option : Volet Battant ALU ({vb_type})",
                quantity=1.0,
                unit_price=vb_price
            ))
            
        # 2. Frais de Pose
        pose_type = annexes.get("frais_pose", "Aucun")
        if pose_type != "Aucun":
            pose_price = 100 if pose_type == "Standard" else (180 if pose_type == "Renovation" else 300)
            db.add(models.SaleOrderLine(
                order_id=sale.id,
                description=f"Prestation : Pose {pose_type}",
                quantity=1.0,
                unit_price=pose_price
            ))
            
        # 3. Moustiquaire
        if annexes.get("moustiquaire"):
            db.add(models.SaleOrderLine(
                order_id=sale.id,
                description="Accessoire : Moustiquaire intégrée",
                quantity=1.0,
                unit_price=85.0
            ))
            
        # 4. Livraison
        if annexes.get("livraison"):
            db.add(models.SaleOrderLine(
                order_id=sale.id,
                description="Logistique : Frais de livraison sur chantier",
                quantity=1.0,
                unit_price=50.0
            ))
            
        db_item.sale_order_id = sale.id
    else:
        existing_sale.status = "SENT"
        existing_sale.workflow_type = "FABRICATION_FROM_MEASURE"
        db_item.sale_order_id = existing_sale.id
        
    db_item.quote_sent_at = utcnow()
    db.commit()
    
    return {"message": "Devis CRM généré et envoyé au client.", "sent_at": db_item.quote_sent_at}

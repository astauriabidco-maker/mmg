from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import List, Optional
import os
import base64
import uuid
from datetime import datetime
from ..database import get_db
from .. import models, schemas
from ..core import security
from ..core import uploads
from ..services.document_sequences import next_number
from ..core.time import utcnow

router = APIRouter(
    prefix="/v2/mmg",
    tags=["mmg"],
    dependencies=[Depends(security.get_current_user)],
)

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
        sale_order_id=mission.sale_order_id,
        assigned_user_id=mission.assigned_user_id,
        assigned_user_name=assigned_user_name,
        status=mission.status,
        purpose=mission.purpose,
        scheduled_start=mission.scheduled_start,
        scheduled_end=mission.scheduled_end,
        notes=mission.notes,
        dossier_ids=[dossier.id for dossier in mission.dossiers],
        openings=mission.openings,
        created_by=mission.created_by,
        created_at=mission.created_at,
        updated_at=mission.updated_at,
    )


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
    site = models.ClientSiteAddress(client_id=client_id, **payload)
    db.add(site)
    db.flush()
    return site


MISSION_TRANSITIONS = {
    models.MeasureMissionStatus.DRAFT.value: {
        models.MeasureMissionStatus.TO_SCHEDULE.value,
        models.MeasureMissionStatus.SCHEDULED.value,
        models.MeasureMissionStatus.CANCELLED.value,
    },
    models.MeasureMissionStatus.TO_SCHEDULE.value: {
        models.MeasureMissionStatus.SCHEDULED.value,
        models.MeasureMissionStatus.CANCELLED.value,
    },
    models.MeasureMissionStatus.SCHEDULED.value: {
        models.MeasureMissionStatus.ON_SITE.value,
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

BE_REVIEW_ROLES = {"ADMIN", "MANAGER", "QUALITY_CONTROLLER", "WORKSHOP_LEAD"}


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


@router.get("/sites", response_model=List[schemas.ClientSiteAddressResponse])
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


@router.post("/sites", response_model=schemas.ClientSiteAddressResponse)
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


@router.put("/sites/{site_id}", response_model=schemas.ClientSiteAddressResponse)
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
    status: Optional[schemas.MeasureMissionStatus] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.MeasureMission)
    if client_id:
        query = query.filter(models.MeasureMission.client_id == client_id)
    if status:
        query = query.filter(models.MeasureMission.status == status.value)
    missions = query.order_by(models.MeasureMission.created_at.desc()).all()
    return [_serialize_mission(mission) for mission in missions]


@router.post("/missions", response_model=schemas.MeasureMissionResponse)
def create_measure_mission(
    item: schemas.MeasureMissionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    client = db.query(models.Client).filter(models.Client.id == item.client_id).first()
    if not client:
        raise HTTPException(404, "Client introuvable")
    site = _resolve_site(db, item.client_id, item.site_address_id, item.site)
    if item.sale_order_id and not db.query(models.SaleOrder).filter(models.SaleOrder.id == item.sale_order_id).first():
        raise HTTPException(404, "Devis introuvable")
    if item.assigned_user_id:
        assigned_user = db.query(models.User).filter(models.User.id == item.assigned_user_id).first()
        if not assigned_user or not assigned_user.is_active:
            raise HTTPException(400, "Technicien introuvable ou inactif")
    if item.status == schemas.MeasureMissionStatus.SCHEDULED:
        if not site:
            raise HTTPException(422, "Une adresse chantier est obligatoire pour planifier la mission")
        if not item.assigned_user_id or not item.scheduled_start:
            raise HTTPException(422, "Affectez un métreur et une date avant de planifier")
    if item.scheduled_start and item.scheduled_end and item.scheduled_end <= item.scheduled_start:
        raise HTTPException(422, "La fin planifiée doit être postérieure au début")
    mission = models.MeasureMission(
        reference=next_number(db, "measure_mission"),
        client_id=item.client_id,
        site_address_id=site.id if site else None,
        sale_order_id=item.sale_order_id,
        assigned_user_id=item.assigned_user_id,
        status=item.status.value,
        purpose=item.purpose,
        scheduled_start=item.scheduled_start,
        scheduled_end=item.scheduled_end,
        notes=item.notes,
        created_by=current_user.get("sub", "Système"),
    )
    db.add(mission)
    db.commit()
    db.refresh(mission)
    return _serialize_mission(mission)


@router.get("/missions/{mission_id}", response_model=schemas.MeasureMissionResponse)
def get_measure_mission(mission_id: int, db: Session = Depends(get_db)):
    mission = _get_mission_or_404(db, mission_id)
    return _serialize_mission(mission)


@router.put("/missions/{mission_id}", response_model=schemas.MeasureMissionResponse)
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
    if site_data is not None or site_address_id is not None:
        site_schema = schemas.ClientSiteAddressCreate(**site_data) if site_data else None
        site = _resolve_site(db, mission.client_id, site_address_id, site_schema)
        mission.site_address_id = site.id if site else None
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
    if mission.scheduled_start and mission.assigned_user_id and mission.status in {
        models.MeasureMissionStatus.DRAFT.value,
        models.MeasureMissionStatus.TO_SCHEDULE.value,
    }:
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


@router.delete("/missions/{mission_id}/openings/{opening_id}")
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


@router.patch("/missions/{mission_id}/status", response_model=schemas.MeasureMissionResponse)
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
        if not mission.assigned_user_id or not mission.scheduled_start:
            raise HTTPException(422, "Affectez un métreur et une date avant de planifier")
    if target == models.MeasureMissionStatus.TO_REVIEW.value:
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
        else:
            for opening in mission.openings:
                if opening.status != schemas.MeasureOpeningStatus.VALIDATED.value:
                    opening.status = schemas.MeasureOpeningStatus.CORRECTION_REQUIRED.value
    mission.status = target
    db.commit()
    db.refresh(mission)
    return _serialize_mission(mission)

@router.post("/", response_model=schemas.MMGResponse)
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

@router.post("/from-sale/{sale_id}", response_model=schemas.MMGResponse)
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

@router.patch("/{dossier_id}/status", response_model=schemas.MMGResponse)
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

@router.post("/{dossier_id}/send-quote")
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

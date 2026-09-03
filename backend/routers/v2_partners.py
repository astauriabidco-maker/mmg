import csv
import io
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..core import security
from ..core.time import utcnow
from ..database import get_db
from ..services.crm_clients import (
    contact_duplicate_groups,
    duplicate_candidates,
    duplicate_groups,
    merge_clients,
    normalize_email,
    normalize_phone,
    normalize_tags,
    normalize_text,
)


router = APIRouter(
    prefix="/v2/partners",
    tags=["partners"],
    dependencies=[Depends(security.get_current_user)],
)

CRM_VIEW = [Depends(security.require_permissions("SALES_VIEW"))]
CRM_EDIT = [Depends(security.require_permissions("SALES_EDIT"))]
ADMIN_ONLY = [Depends(security.require_roles("ADMIN", "SUPER_ADMIN"))]
MAX_CLIENT_IMPORT_BYTES = 2 * 1024 * 1024
CLIENT_CSV_FIELDS = (
    "name",
    "contact_name",
    "email",
    "phone",
    "address",
    "country",
    "tax_id",
    "customer_type",
    "segment",
    "tags",
    "is_active",
)
CONTACT_INFLUENCE_ROLES = {
    "DECISION_MAKER",
    "PRESCRIBER",
    "BUYER",
    "SITE_CONTACT",
    "TECHNICAL_CONTACT",
    "ACCOUNTING",
    "OTHER",
}
CONTACT_CHANNELS = {"EMAIL", "PHONE", "SMS", "WHATSAPP", "IN_PERSON"}


def _client_or_404(db: Session, client_id: int) -> models.Client:
    client = (
        db.query(models.Client)
        .options(selectinload(models.Client.contacts))
        .filter(models.Client.id == client_id)
        .first()
    )
    if not client:
        raise HTTPException(404, "Client introuvable")
    return client


def _normalize_client_payload(payload: dict) -> dict:
    payload["name"] = str(payload.get("name") or "").strip()
    if not payload["name"]:
        raise HTTPException(422, "Le nom du client est obligatoire")
    payload["segment"] = (payload.get("segment") or "").strip() or None
    payload["tags"] = normalize_tags(payload.get("tags"))
    for field in ("contact_name", "email", "phone", "address", "country", "tax_id"):
        if field in payload and isinstance(payload[field], str):
            payload[field] = payload[field].strip() or None
    return payload


def _create_primary_contact_from_client(
    db: Session,
    client: models.Client,
) -> None:
    if not any((client.contact_name, client.email, client.phone)):
        return
    db.add(
        models.ClientContact(
            client_id=client.id,
            name=client.contact_name or client.email or client.phone,
            role="Contact principal",
            priority=1,
            influence_role="DECISION_MAKER",
            preferred_channel="EMAIL" if client.email else "PHONE" if client.phone else None,
            email_consent=False,
            email=client.email,
            phone=client.phone,
            is_primary=True,
        )
    )


def _update_primary_contact_from_client(
    db: Session,
    client: models.Client,
) -> None:
    primary = (
        db.query(models.ClientContact)
        .filter(
            models.ClientContact.client_id == client.id,
            models.ClientContact.is_primary.is_(True),
        )
        .first()
    )
    if primary is None:
        _create_primary_contact_from_client(db, client)
        return
    if client.contact_name:
        primary.name = client.contact_name
    primary.email = client.email
    primary.phone = client.phone


def _sync_primary_contact(
    db: Session,
    client: models.Client,
    primary: Optional[models.ClientContact] = None,
) -> None:
    contacts = (
        db.query(models.ClientContact)
        .filter(models.ClientContact.client_id == client.id)
        .order_by(
            models.ClientContact.is_primary.desc(),
            models.ClientContact.created_at.asc(),
            models.ClientContact.id.asc(),
        )
        .all()
    )
    if primary is None and contacts:
        primary = contacts[0]
    for contact in contacts:
        contact.is_primary = bool(primary and contact.id == primary.id)
    if primary:
        client.contact_name = primary.name
        client.email = primary.email
        client.phone = primary.phone
    else:
        client.contact_name = None
        client.email = None
        client.phone = None


def _normalize_contact_payload(payload: dict) -> dict:
    if "name" in payload:
        payload["name"] = (payload["name"] or "").strip()
        if not payload["name"]:
            raise HTTPException(422, "Le nom du contact est obligatoire")
    for field in ("role", "email", "phone", "notes"):
        if field in payload and isinstance(payload[field], str):
            payload[field] = payload[field].strip() or None
    if "influence_role" in payload:
        payload["influence_role"] = (payload["influence_role"] or "").strip().upper() or None
        if payload["influence_role"] and payload["influence_role"] not in CONTACT_INFLUENCE_ROLES:
            raise HTTPException(422, "Rôle d'influence contact invalide")
    if "preferred_channel" in payload:
        payload["preferred_channel"] = (payload["preferred_channel"] or "").strip().upper() or None
        if payload["preferred_channel"] and payload["preferred_channel"] not in CONTACT_CHANNELS:
            raise HTTPException(422, "Canal préféré contact invalide")
    if payload.get("email_consent") is False:
        payload["email_consent_at"] = None
    if payload.get("email_consent") is True and not payload.get("email_consent_at"):
        payload["email_consent_at"] = utcnow()
    return payload


def _find_import_match(db: Session, row: dict) -> Optional[models.Client]:
    email = normalize_email(row.get("email"))
    phone = normalize_phone(row.get("phone"))
    name = normalize_text(row.get("name"))
    for client in db.query(models.Client).all():
        if email and normalize_email(client.email) == email:
            return client
        if phone and normalize_phone(client.phone) == phone:
            return client
        if name and normalize_text(client.name) == name:
            return client
    return None


def _is_recipe_fixture_client(client: models.Client) -> bool:
    markers = [
        client.name,
        client.contact_name,
        client.email,
        client.phone,
        client.tax_id,
        client.segment,
        *(client.tags or []),
    ]
    normalized_markers = " ".join(normalize_text(value) for value in markers if value)
    return any(
        marker in normalized_markers
        for marker in (
            "recette doublon",
            "recette crm",
            "fixture",
            "test a supprimer",
            "a supprimer",
        )
    )


def _delete_recipe_fixture_client_graph(db: Session, client: models.Client) -> None:
    opportunity_ids = [
        item[0]
        for item in db.query(models.CRMOpportunity.id)
        .filter(models.CRMOpportunity.client_id == client.id)
        .all()
    ]
    site_ids = [
        item[0]
        for item in db.query(models.ClientSiteAddress.id)
        .filter(models.ClientSiteAddress.client_id == client.id)
        .all()
    ]
    mission_ids = [
        item[0]
        for item in db.query(models.MeasureMission.id)
        .filter(models.MeasureMission.client_id == client.id)
        .all()
    ]

    db.query(models.CalendarTask).filter(
        models.CalendarTask.client_id == client.id
    ).update({models.CalendarTask.client_id: None}, synchronize_session=False)
    if opportunity_ids:
        db.query(models.CalendarTask).filter(
            models.CalendarTask.opportunity_id.in_(opportunity_ids)
        ).update({models.CalendarTask.opportunity_id: None}, synchronize_session=False)
        db.query(models.CRMReminderPlan).filter(
            models.CRMReminderPlan.opportunity_id.in_(opportunity_ids)
        ).update({models.CRMReminderPlan.sent_delivery_id: None}, synchronize_session=False)
        db.query(models.CRMReminderDelivery).filter(
            models.CRMReminderDelivery.opportunity_id.in_(opportunity_ids)
        ).update(
            {
                models.CRMReminderDelivery.opportunity_id: None,
                models.CRMReminderDelivery.activity_id: None,
            },
            synchronize_session=False,
        )
        db.query(models.CRMOpportunityStageHistory).filter(
            models.CRMOpportunityStageHistory.opportunity_id.in_(opportunity_ids)
        ).delete(synchronize_session=False)
        db.query(models.CRMReminderPlan).filter(
            models.CRMReminderPlan.opportunity_id.in_(opportunity_ids)
        ).delete(synchronize_session=False)

    db.query(models.CRMReminderPlan).filter(
        models.CRMReminderPlan.client_id == client.id
    ).update({models.CRMReminderPlan.sent_delivery_id: None}, synchronize_session=False)
    db.query(models.CRMReminderPlan).filter(
        models.CRMReminderPlan.client_id == client.id
    ).delete(synchronize_session=False)
    db.query(models.CRMReminderDelivery).filter(
        models.CRMReminderDelivery.client_id == client.id
    ).delete(synchronize_session=False)
    db.query(models.CRMActivity).filter(
        models.CRMActivity.client_id == client.id
    ).delete(synchronize_session=False)
    if opportunity_ids:
        db.query(models.CRMOpportunity).filter(
            models.CRMOpportunity.id.in_(opportunity_ids)
        ).delete(synchronize_session=False)

    db.query(models.MMG).filter(models.MMG.client_id == client.id).update(
        {
            models.MMG.client_id: None,
            models.MMG.client_name: f"{client.name} (fiche recette supprimée)",
        },
        synchronize_session=False,
    )
    if site_ids:
        db.query(models.MMG).filter(models.MMG.site_address_id.in_(site_ids)).update(
            {models.MMG.site_address_id: None},
            synchronize_session=False,
        )
    if mission_ids:
        db.query(models.MMG).filter(models.MMG.measure_mission_id.in_(mission_ids)).update(
            {models.MMG.measure_mission_id: None},
            synchronize_session=False,
        )
        for mission in (
            db.query(models.MeasureMission)
            .filter(models.MeasureMission.id.in_(mission_ids))
            .all()
        ):
            db.delete(mission)

    db.delete(client)


@router.get(
    "/clients",
    response_model=List[schemas.ClientResponse],
    dependencies=CRM_VIEW,
)
def get_clients(
    search: Optional[str] = None,
    segment: Optional[str] = None,
    tag: Optional[str] = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(models.Client).options(selectinload(models.Client.contacts))
    if not include_inactive:
        query = query.filter(models.Client.is_active.is_(True))
    if segment:
        query = query.filter(
            func.lower(models.Client.segment) == segment.strip().lower()
        )
    if search:
        pattern = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(models.Client.name).like(pattern),
                func.lower(func.coalesce(models.Client.contact_name, "")).like(pattern),
                func.lower(func.coalesce(models.Client.email, "")).like(pattern),
                func.lower(func.coalesce(models.Client.phone, "")).like(pattern),
            )
        )
    clients = query.order_by(models.Client.name.asc()).all()
    if tag:
        normalized_tag = normalize_text(tag)
        clients = [
            client
            for client in clients
            if normalized_tag in {normalize_text(item) for item in client.tags or []}
        ]
    return clients


@router.get(
    "/client-segments",
    response_model=List[str],
    dependencies=CRM_VIEW,
)
def list_client_segments(db: Session = Depends(get_db)):
    values = (
        db.query(models.Client.segment)
        .filter(models.Client.segment.is_not(None))
        .distinct()
        .all()
    )
    return sorted({value[0].strip() for value in values if value[0] and value[0].strip()})


@router.get("/clients/export.csv", dependencies=CRM_VIEW)
def export_clients_csv(db: Session = Depends(get_db)):
    clients = (
        db.query(models.Client)
        .options(selectinload(models.Client.contacts))
        .order_by(models.Client.name.asc())
        .all()
    )
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CLIENT_CSV_FIELDS)
    writer.writeheader()
    for client in clients:
        writer.writerow(
            {
                "name": client.name,
                "contact_name": client.contact_name or "",
                "email": client.email or "",
                "phone": client.phone or "",
                "address": client.address or "",
                "country": client.country or "",
                "tax_id": client.tax_id or "",
                "customer_type": client.customer_type or "",
                "segment": client.segment or "",
                "tags": ";".join(client.tags or []),
                "is_active": "true" if client.is_active else "false",
            }
        )
    content = "\ufeff" + output.getvalue()
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="clients-crm.csv"'},
    )


@router.post(
    "/clients/import",
    response_model=schemas.ClientImportResponse,
    dependencies=CRM_EDIT,
)
async def import_clients_csv(
    file: UploadFile = File(...),
    update_existing: bool = False,
    db: Session = Depends(get_db),
):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(422, "Importez un fichier CSV")
    content = await file.read(MAX_CLIENT_IMPORT_BYTES + 1)
    if len(content) > MAX_CLIENT_IMPORT_BYTES:
        raise HTTPException(413, "Le fichier CSV dépasse 2 Mo")
    try:
        text_content = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(422, "Le fichier CSV doit être encodé en UTF-8") from exc

    reader = csv.DictReader(io.StringIO(text_content))
    if not reader.fieldnames or "name" not in {
        (field or "").strip().lower() for field in reader.fieldnames
    }:
        raise HTTPException(422, "La colonne « name » est obligatoire")

    created = updated = skipped = 0
    errors: list[str] = []
    for line_number, raw_row in enumerate(reader, start=2):
        row = {
            str(key or "").strip().lower(): str(value or "").strip()
            for key, value in raw_row.items()
        }
        if not row.get("name"):
            errors.append(f"Ligne {line_number}: nom client manquant")
            continue
        existing = _find_import_match(db, row)
        if existing and not update_existing:
            skipped += 1
            continue
        tags = normalize_tags(
            part
            for part in row.get("tags", "").replace(",", ";").split(";")
        )
        active_label = row.get("is_active", "true").lower()
        payload = {
            "name": row["name"],
            "contact_name": row.get("contact_name") or None,
            "email": row.get("email") or None,
            "phone": row.get("phone") or None,
            "address": row.get("address") or None,
            "country": row.get("country") or "FR",
            "tax_id": row.get("tax_id") or None,
            "customer_type": row.get("customer_type") or "B2B",
            "segment": row.get("segment") or None,
            "tags": tags,
            "is_active": active_label not in {"0", "false", "no", "non"},
        }
        if existing:
            for field, value in payload.items():
                if value not in (None, "", []):
                    setattr(existing, field, value)
            _update_primary_contact_from_client(db, existing)
            updated += 1
        else:
            client = models.Client(**payload)
            db.add(client)
            db.flush()
            _create_primary_contact_from_client(db, client)
            created += 1
    db.commit()
    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
    }


@router.get(
    "/clients/duplicates",
    response_model=List[schemas.ClientDuplicateGroup],
    dependencies=CRM_VIEW,
)
def list_client_duplicate_groups(db: Session = Depends(get_db)):
    clients = (
        db.query(models.Client)
        .options(selectinload(models.Client.contacts))
        .order_by(models.Client.created_at.asc())
        .all()
    )
    return [
        {"clients": group, "score": score, "reasons": reasons}
        for group, score, reasons in duplicate_groups(clients)
    ]


@router.post(
    "/clients/{target_client_id}/merge",
    response_model=schemas.ClientMergeResponse,
    dependencies=CRM_EDIT,
)
def merge_client_records(
    target_client_id: int,
    item: schemas.ClientMergeRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(security.get_current_user),
):
    if not item.confirm:
        raise HTTPException(409, "Confirmez explicitement la fusion des fiches clients")
    source_ids = sorted(set(item.source_client_ids))
    if target_client_id in source_ids:
        raise HTTPException(422, "La fiche cible ne peut pas être une source")
    if not source_ids:
        raise HTTPException(422, "Sélectionnez au moins une fiche source")
    target = _client_or_404(db, target_client_id)
    sources = (
        db.query(models.Client)
        .filter(models.Client.id.in_(source_ids))
        .order_by(models.Client.id.asc())
        .all()
    )
    if len(sources) != len(source_ids):
        raise HTTPException(404, "Une ou plusieurs fiches sources sont introuvables")
    moved = merge_clients(
        db,
        target,
        sources,
        actor=current_user.get("sub", "Système"),
    )
    db.commit()
    db.refresh(target)
    return {
        "target": target,
        "merged_client_ids": source_ids,
        "moved_records": moved,
    }


@router.get(
    "/clients/{client_id}/duplicates",
    response_model=List[schemas.ClientDuplicateCandidate],
    dependencies=CRM_VIEW,
)
def list_client_duplicate_candidates(
    client_id: int,
    db: Session = Depends(get_db),
):
    reference = _client_or_404(db, client_id)
    clients = (
        db.query(models.Client)
        .options(selectinload(models.Client.contacts))
        .all()
    )
    return [
        {"client": candidate, "score": score, "reasons": reasons}
        for candidate, score, reasons in duplicate_candidates(clients, reference)
    ]


@router.post(
    "/clients",
    response_model=schemas.ClientResponse,
    dependencies=CRM_EDIT,
)
def create_client(client: schemas.ClientCreate, db: Session = Depends(get_db)):
    payload = _normalize_client_payload(client.model_dump())
    existing = (
        db.query(models.Client)
        .filter(func.lower(models.Client.name) == payload["name"].lower())
        .first()
    )
    if existing:
        raise HTTPException(409, "Un client portant ce nom existe déjà")
    db_client = models.Client(**payload)
    db.add(db_client)
    db.flush()
    _create_primary_contact_from_client(db, db_client)
    db.commit()
    db.refresh(db_client)
    return db_client


@router.put(
    "/clients/{client_id}",
    response_model=schemas.ClientResponse,
    dependencies=CRM_EDIT,
)
def update_client(
    client_id: int,
    client: schemas.ClientCreate,
    db: Session = Depends(get_db),
):
    db_client = _client_or_404(db, client_id)
    payload = _normalize_client_payload(client.model_dump())
    duplicate = (
        db.query(models.Client)
        .filter(
            models.Client.id != client_id,
            func.lower(models.Client.name) == payload["name"].lower(),
        )
        .first()
    )
    if duplicate:
        raise HTTPException(409, "Un autre client porte déjà ce nom")
    for key, value in payload.items():
        setattr(db_client, key, value)
    _update_primary_contact_from_client(db, db_client)
    db.commit()
    db.refresh(db_client)
    return db_client


@router.delete("/clients/{client_id}", dependencies=CRM_EDIT)
def delete_client(client_id: int, db: Session = Depends(get_db)):
    db_client = _client_or_404(db, client_id)
    db.delete(db_client)
    db.commit()
    return {"status": "deleted"}


@router.delete(
    "/clients/{client_id}/recipe-fixture",
    dependencies=ADMIN_ONLY,
)
def delete_recipe_fixture_client(client_id: int, db: Session = Depends(get_db)):
    db_client = _client_or_404(db, client_id)
    if not _is_recipe_fixture_client(db_client):
        raise HTTPException(
            422,
            "Cette action est réservée aux fiches de recette/test explicitement identifiées",
        )
    deleted_name = db_client.name
    _delete_recipe_fixture_client_graph(db, db_client)
    db.commit()
    return {"status": "deleted", "deleted_client_id": client_id, "deleted_name": deleted_name}


@router.get(
    "/clients/{client_id}/contacts",
    response_model=List[schemas.ClientContactResponse],
    dependencies=CRM_VIEW,
)
def list_client_contacts(client_id: int, db: Session = Depends(get_db)):
    _client_or_404(db, client_id)
    return (
        db.query(models.ClientContact)
        .filter(models.ClientContact.client_id == client_id)
        .order_by(
            models.ClientContact.is_primary.desc(),
            models.ClientContact.name.asc(),
        )
        .all()
    )


@router.get(
    "/clients/{client_id}/contacts/duplicates",
    response_model=List[schemas.ClientContactDuplicateGroup],
    dependencies=CRM_VIEW,
)
def list_client_contact_duplicate_groups(
    client_id: int,
    db: Session = Depends(get_db),
):
    _client_or_404(db, client_id)
    contacts = (
        db.query(models.ClientContact)
        .filter(models.ClientContact.client_id == client_id)
        .order_by(
            models.ClientContact.is_primary.desc(),
            models.ClientContact.priority.asc(),
            models.ClientContact.name.asc(),
        )
        .all()
    )
    return [
        {"contacts": group, "score": score, "reasons": reasons}
        for group, score, reasons in contact_duplicate_groups(contacts)
    ]


@router.post(
    "/clients/{client_id}/contacts",
    response_model=schemas.ClientContactResponse,
    dependencies=CRM_EDIT,
)
def create_client_contact(
    client_id: int,
    item: schemas.ClientContactCreate,
    db: Session = Depends(get_db),
):
    client = _client_or_404(db, client_id)
    payload = _normalize_contact_payload(item.model_dump())
    existing_count = (
        db.query(models.ClientContact)
        .filter(models.ClientContact.client_id == client_id)
        .count()
    )
    contact = models.ClientContact(
        client_id=client_id,
        name=payload["name"],
        role=payload.get("role"),
        priority=payload.get("priority") or 3,
        influence_role=payload.get("influence_role"),
        preferred_channel=payload.get("preferred_channel"),
        email_consent=bool(payload.get("email_consent")),
        email_consent_at=payload.get("email_consent_at") if payload.get("email_consent") else None,
        email=payload.get("email"),
        phone=payload.get("phone"),
        is_primary=payload.get("is_primary") or existing_count == 0,
        notes=payload.get("notes"),
    )
    db.add(contact)
    db.flush()
    if contact.is_primary:
        _sync_primary_contact(db, client, contact)
    db.commit()
    db.refresh(contact)
    return contact


@router.patch(
    "/clients/{client_id}/contacts/{contact_id}",
    response_model=schemas.ClientContactResponse,
    dependencies=CRM_EDIT,
)
def update_client_contact(
    client_id: int,
    contact_id: int,
    item: schemas.ClientContactUpdate,
    db: Session = Depends(get_db),
):
    client = _client_or_404(db, client_id)
    contact = (
        db.query(models.ClientContact)
        .filter(
            models.ClientContact.id == contact_id,
            models.ClientContact.client_id == client_id,
        )
        .first()
    )
    if not contact:
        raise HTTPException(404, "Contact introuvable")
    payload = item.model_dump(exclude_unset=True)
    payload = _normalize_contact_payload(payload)
    for key, value in payload.items():
        setattr(contact, key, value)
    db.flush()
    if contact.is_primary:
        _sync_primary_contact(db, client, contact)
    else:
        current_primary = (
            db.query(models.ClientContact)
            .filter(
                models.ClientContact.client_id == client_id,
                models.ClientContact.is_primary.is_(True),
            )
            .first()
        )
        _sync_primary_contact(db, client, current_primary)
    db.commit()
    db.refresh(contact)
    return contact


@router.delete(
    "/clients/{client_id}/contacts/{contact_id}",
    status_code=204,
    dependencies=CRM_EDIT,
)
def delete_client_contact(
    client_id: int,
    contact_id: int,
    db: Session = Depends(get_db),
):
    client = _client_or_404(db, client_id)
    contact = (
        db.query(models.ClientContact)
        .filter(
            models.ClientContact.id == contact_id,
            models.ClientContact.client_id == client_id,
        )
        .first()
    )
    if not contact:
        raise HTTPException(404, "Contact introuvable")
    was_primary = contact.is_primary
    db.delete(contact)
    db.flush()
    if was_primary:
        _sync_primary_contact(db, client)
    db.commit()


# NOTE: le CRUD fournisseurs est unifié sur /v2/suppliers.

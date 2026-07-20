from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from ..database import get_db
from .. import models, schemas
from ..core.security import get_current_user, get_current_user_role, require_roles
import time
import io
import tempfile
from pathlib import Path
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill
from sqlalchemy import or_
from ..services.bom_parser import parse_bom_file
from ..services.stock_reservations import (
    annotate_variant_availability,
    build_preview_payload,
    cancel_reservation,
    consume_reservation,
    create_reservation,
)
from ..services.stock_service import InventoryService
from scripts.import_workshop_debits import parse_file
from ..core.time import utcnow

router = APIRouter(
    prefix="/v2/stock",
    tags=["stock"],
    dependencies=[Depends(get_current_user)],
)


async def _parse_workshop_uploads(files: List[UploadFile]):
    records = []
    issues = []
    source_names = []
    for file in files:
        suffix = Path(file.filename or "").suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = Path(tmp.name)
        try:
            parsed_records, parsed_issues = parse_file(tmp_path)
            source_name = file.filename or tmp_path.name
            for record in parsed_records:
                object.__setattr__(record, "source", source_name)
            for issue in parsed_issues:
                object.__setattr__(issue, "source", source_name)
            records.extend(parsed_records)
            issues.extend(parsed_issues)
            source_names.append(source_name)
        finally:
            tmp_path.unlink(missing_ok=True)
    return records, issues, source_names


def _require_stock_manager(user: dict) -> None:
    if user.get("role") not in ["ADMIN", "MANAGER"]:
        raise HTTPException(status_code=403, detail="Seul un manager peut gérer l'inventaire physique.")


def _get_quant_quantity(db: Session, variant_id: int, location_id: int) -> float:
    quant = db.query(models.StockQuant).filter_by(variant_id=variant_id, location_id=location_id).first()
    return float(quant.quantity if quant else 0)


def _get_or_create_quant(db: Session, variant_id: int, location_id: int) -> models.StockQuant:
    quant = db.query(models.StockQuant).filter_by(variant_id=variant_id, location_id=location_id).first()
    if not quant:
        quant = models.StockQuant(variant_id=variant_id, location_id=location_id, quantity=0)
        db.add(quant)
        db.flush()
    return quant


def _get_or_create_inventory_location(db: Session) -> models.StockLocation:
    location = db.query(models.StockLocation).filter_by(name="Virtual/Inventory", usage="inventory").first()
    if not location:
        location = models.StockLocation(name="Virtual/Inventory", usage="inventory", is_active=True)
        db.add(location)
        db.flush()
    return location


def _line_status_from_variance(variance: float) -> str:
    return "ok" if abs(float(variance or 0)) <= 0.000001 else "variance"


def _locked_inventory_session_for_location(db: Session, location_id: int) -> Optional[models.InventorySession]:
    location = db.query(models.StockLocation).filter_by(id=location_id, is_active=True).first()
    if not location or location.usage != "internal":
        return None
    return (
        db.query(models.InventorySession)
        .filter(
            models.InventorySession.zone_locked == True,
            models.InventorySession.status.in_(["draft", "counting"]),
            or_(
                models.InventorySession.location_id == None,
                models.InventorySession.location_id == location_id,
            ),
        )
        .order_by(models.InventorySession.created_at.desc())
        .first()
    )


def _assert_location_not_locked(db: Session, location_id: int) -> None:
    locked_session = _locked_inventory_session_for_location(db, location_id)
    if locked_session:
        raise HTTPException(
            status_code=423,
            detail=(
                f"Zone gelée par la campagne d'inventaire {locked_session.reference}. "
                "Validez ou annulez la campagne avant de créer un mouvement stock."
            ),
        )


def _sync_variant_internal_stock(db: Session, variant_id: int) -> None:
    variant = db.query(models.ProductVariant).filter_by(id=variant_id).first()
    if not variant:
        return
    internal_quants = (
        db.query(models.StockQuant)
        .join(models.StockLocation, models.StockQuant.location_id == models.StockLocation.id)
        .filter(
            models.StockQuant.variant_id == variant_id,
            models.StockLocation.usage == "internal",
            models.StockLocation.is_active == True,
        )
        .all()
    )
    variant.quantity_in_stock = sum(float(quant.quantity or 0) for quant in internal_quants)


@router.get("/inventory-sessions", response_model=List[schemas.InventorySessionResponse])
def list_inventory_sessions(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    query = db.query(models.InventorySession).options(
        joinedload(models.InventorySession.location),
        joinedload(models.InventorySession.lines).joinedload(models.InventoryCountLine.variant),
        joinedload(models.InventorySession.lines).joinedload(models.InventoryCountLine.location),
    ).order_by(models.InventorySession.created_at.desc())
    if status:
        query = query.filter(models.InventorySession.status == status)
    return query.limit(50).all()


@router.post("/inventory-sessions", response_model=schemas.InventorySessionResponse)
def create_inventory_session(
    payload: schemas.InventorySessionCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    _require_stock_manager(user)
    if payload.location_id:
        location = db.query(models.StockLocation).filter_by(id=payload.location_id, is_active=True).first()
        if not location:
            raise HTTPException(status_code=404, detail="Emplacement introuvable.")
    reference = f"INV-{int(time.time() * 1000)}"
    session = models.InventorySession(
        reference=reference,
        name=payload.name.strip(),
        location_id=payload.location_id,
        notes=payload.notes,
        status="draft",
        zone_locked=payload.zone_locked,
        locked_at=utcnow() if payload.zone_locked else None,
        unlocked_at=None if payload.zone_locked else utcnow(),
        created_by=user.get("sub", "Admin"),
    )
    if not session.name:
        raise HTTPException(status_code=400, detail="Nom de campagne obligatoire.")
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/inventory-sessions/{session_id}", response_model=schemas.InventorySessionResponse)
def get_inventory_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    session = (
        db.query(models.InventorySession)
        .options(
            joinedload(models.InventorySession.location),
            joinedload(models.InventorySession.lines).joinedload(models.InventoryCountLine.variant).joinedload(models.ProductVariant.product),
            joinedload(models.InventorySession.lines).joinedload(models.InventoryCountLine.location),
        )
        .filter(models.InventorySession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Campagne d'inventaire introuvable.")
    return session


@router.post("/inventory-sessions/{session_id}/lines", response_model=schemas.InventoryCountLineResponse)
def upsert_inventory_count_line(
    session_id: int,
    payload: schemas.InventoryCountLineUpsert,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    _require_stock_manager(user)
    session = db.query(models.InventorySession).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Campagne d'inventaire introuvable.")
    if session.status in ["validated", "cancelled"]:
        raise HTTPException(status_code=400, detail="Campagne clôturée.")
    variant = db.query(models.ProductVariant).filter_by(id=payload.variant_id).first()
    if not variant:
        raise HTTPException(status_code=404, detail="Variante introuvable.")
    location = db.query(models.StockLocation).filter_by(id=payload.location_id, is_active=True).first()
    if not location:
        raise HTTPException(status_code=404, detail="Emplacement introuvable.")
    if location.usage != "internal":
        raise HTTPException(status_code=400, detail="Le comptage physique doit viser un emplacement interne.")
    if session.location_id and session.location_id != payload.location_id:
        raise HTTPException(status_code=400, detail="Cette campagne est limitée à un autre emplacement.")
    if payload.counted_quantity < 0:
        raise HTTPException(status_code=400, detail="La quantité comptée ne peut pas être négative.")

    expected = _get_quant_quantity(db, payload.variant_id, payload.location_id)
    counted = float(payload.counted_quantity)
    line = (
        db.query(models.InventoryCountLine)
        .filter_by(session_id=session_id, variant_id=payload.variant_id, location_id=payload.location_id)
        .first()
    )
    if not line:
        line = models.InventoryCountLine(
            session_id=session_id,
            variant_id=payload.variant_id,
            location_id=payload.location_id,
        )
        db.add(line)
    line.expected_quantity = expected
    line.counted_quantity = counted
    line.variance_quantity = counted - expected
    line.status = _line_status_from_variance(line.variance_quantity)
    line.reason = payload.reason
    line.notes = payload.notes
    line.recount_requested_by = None
    line.recount_requested_at = None
    line.recount_notes = None
    line.counted_by = user.get("sub", "Admin")
    line.counted_at = utcnow()
    session.status = "counting"
    db.commit()
    db.refresh(line)
    return line


@router.post("/inventory-sessions/{session_id}/lines/{line_id}/recount", response_model=schemas.InventoryCountLineResponse)
def request_inventory_line_recount(
    session_id: int,
    line_id: int,
    payload: schemas.InventoryRecountRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    _require_stock_manager(user)
    session = db.query(models.InventorySession).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Campagne d'inventaire introuvable.")
    if session.status in ["validated", "cancelled"]:
        raise HTTPException(status_code=400, detail="Campagne clôturée.")
    line = (
        db.query(models.InventoryCountLine)
        .filter_by(id=line_id, session_id=session_id)
        .first()
    )
    if not line:
        raise HTTPException(status_code=404, detail="Ligne de comptage introuvable.")
    if abs(float(line.variance_quantity or 0)) <= 0.000001:
        raise HTTPException(status_code=400, detail="Cette ligne est déjà conforme.")
    line.status = "recount"
    line.recount_requested_by = user.get("sub", "Admin")
    line.recount_requested_at = utcnow()
    line.recount_notes = payload.notes
    db.commit()
    db.refresh(line)
    return line


@router.post("/inventory-sessions/{session_id}/validate", response_model=schemas.InventorySessionResponse)
def validate_inventory_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    _require_stock_manager(user)
    session = (
        db.query(models.InventorySession)
        .options(joinedload(models.InventorySession.lines))
        .filter(models.InventorySession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Campagne d'inventaire introuvable.")
    if session.status == "validated":
        raise HTTPException(status_code=400, detail="Campagne déjà validée.")
    if session.status == "cancelled":
        raise HTTPException(status_code=400, detail="Campagne annulée.")
    if not session.lines:
        raise HTTPException(status_code=400, detail="Aucune ligne comptée à valider.")
    recount_lines = [line for line in session.lines if line.status == "recount"]
    if recount_lines:
        raise HTTPException(
            status_code=400,
            detail=f"{len(recount_lines)} ligne(s) sont en attente de recompte.",
        )

    inventory_location = _get_or_create_inventory_location(db)
    author = user.get("sub", "Admin")
    for line in session.lines:
        current_qty = _get_quant_quantity(db, line.variant_id, line.location_id)
        if abs(current_qty - float(line.expected_quantity or 0)) > 0.000001:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Stock modifié depuis le comptage. "
                    f"Relancez la ligne {line.variant_id} avant validation."
                ),
            )
        variance = float(line.variance_quantity or 0)
        if abs(variance) <= 0.000001:
            continue
        if not (line.reason or "").strip():
            raise HTTPException(
                status_code=400,
                detail=(
                    "Motif obligatoire pour valider un écart d'inventaire. "
                    f"Ligne {line.id}: renseignez la raison du comptage."
                ),
            )

        if variance > 0:
            source_id = inventory_location.id
            dest_id = line.location_id
            quantity = variance
        else:
            adjustment = abs(variance)
            source_id = line.location_id
            dest_id = inventory_location.id
            quantity = adjustment

        try:
            result = InventoryService.move_stock(
                db,
                variant_id=line.variant_id,
                source_location_id=source_id,
                dest_location_id=dest_id,
                quantity=quantity,
                reference=f"INV/{session.reference}/{line.id}",
                notes=f"Ajustement inventaire physique {session.reference}. Motif: {line.reason or 'Non renseigné'}",
                author=author,
                source_screen="stock.physical_inventory",
                document_type="inventory_session",
                document_reference=session.reference,
                business_reason=line.reason,
                enforce_zone_lock=False,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Ajustement impossible: {exc}") from exc
        line.adjustment_move_id = result.move.id
        line.status = "validated"

    for line in session.lines:
        line.status = "validated"

    session.status = "validated"
    session.validated_by = author
    session.validated_at = utcnow()
    session.zone_locked = False
    session.unlocked_at = utcnow()
    db.commit()
    db.refresh(session)
    return get_inventory_session(session.id, db, user)


@router.post("/inventory-sessions/{session_id}/cancel", response_model=schemas.InventorySessionResponse)
def cancel_inventory_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    _require_stock_manager(user)
    session = db.query(models.InventorySession).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Campagne d'inventaire introuvable.")
    if session.status == "validated":
        raise HTTPException(status_code=400, detail="Campagne déjà validée.")
    session.status = "cancelled"
    session.zone_locked = False
    session.unlocked_at = utcnow()
    db.commit()
    db.refresh(session)
    return session


@router.get("/inventory-sessions/{session_id}/export")
def export_inventory_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    session = (
        db.query(models.InventorySession)
        .options(
            joinedload(models.InventorySession.location),
            joinedload(models.InventorySession.lines).joinedload(models.InventoryCountLine.variant).joinedload(models.ProductVariant.product),
            joinedload(models.InventorySession.lines).joinedload(models.InventoryCountLine.location),
        )
        .filter(models.InventorySession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Campagne d'inventaire introuvable.")

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Inventaire physique"
    sheet.append(["Campagne", session.reference, session.name])
    sheet.append(["Statut", session.status, "Zone gelée" if session.zone_locked else "Zone libérée"])
    sheet.append(["Emplacement", session.location.name if session.location else "Tous emplacements internes"])
    sheet.append([])
    headers = [
        "Référence",
        "Produit",
        "Emplacement",
        "Système",
        "Compté",
        "Écart",
        "Statut ligne",
        "Motif",
        "Recompte demandé par",
        "Note recompte",
        "Mouvement ajustement",
    ]
    sheet.append(headers)
    header_row = sheet.max_row
    for cell in sheet[header_row]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1E293B")

    for line in session.lines:
        variant = line.variant
        product = variant.product if variant else None
        sheet.append([
            variant.reference if variant else f"Variante #{line.variant_id}",
            product.name if product else "",
            line.location.name if line.location else f"Lieu #{line.location_id}",
            float(line.expected_quantity or 0),
            float(line.counted_quantity or 0),
            float(line.variance_quantity or 0),
            line.status,
            line.reason or "",
            line.recount_requested_by or "",
            line.recount_notes or "",
            line.adjustment_move_id or "",
        ])

    for column in sheet.columns:
        max_length = max(len(str(cell.value or "")) for cell in column)
        sheet.column_dimensions[column[0].column_letter].width = min(max(max_length + 2, 12), 44)

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    filename = f"{session.reference}-rapport-inventaire.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.get("/products", response_model=List[schemas.ProductResponse])
def get_products(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    products = db.query(models.Product).options(joinedload(models.Product.variants)).all()
    for product in products:
        for variant in product.variants:
            annotate_variant_availability(db, variant)
    return products

@router.post("/products", response_model=schemas.ProductResponse)
def create_product(product_data: schemas.ProductCreate, db: Session = Depends(get_db), role: str = Depends(get_current_user_role)):
    if role not in ["ADMIN", "MANAGER"]:
        raise HTTPException(status_code=403, detail="Seul un manager peut créer des produits.")
    
    existing = db.query(models.Product).filter(models.Product.reference_base == product_data.reference_base).first()
    if existing: raise HTTPException(400, "Base reference already exists")
    
    new_product = models.Product(**product_data.model_dump(exclude={'variants'}))
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    
    for v_data in product_data.variants:
        new_variant = models.ProductVariant(product_id=new_product.id, **v_data.model_dump())
        db.add(new_variant)
    db.commit()
    db.refresh(new_product)
    return new_product

@router.put("/products/{product_id}", response_model=schemas.ProductResponse)
def update_product(product_id: int, product_data: schemas.ProductBase, db: Session = Depends(get_db), role: str = Depends(get_current_user_role)):
    if role not in ["ADMIN", "MANAGER"]:
        raise HTTPException(status_code=403, detail="Seul un manager peut modifier des produits.")
        
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product: raise HTTPException(404, "Product not found")
    for key, value in product_data.model_dump().items(): setattr(product, key, value)
    db.commit()
    db.refresh(product)
    return product

import os
import uuid
import shutil
from ..core import uploads

@router.post("/products/upload_image")
async def upload_product_image(file: UploadFile = File(...), role: str = Depends(get_current_user_role)):
    if role not in ["ADMIN", "MANAGER"]:
        raise HTTPException(status_code=403, detail="Non autorisé.")

    filepath = await uploads.save_upload_file(file, os.path.join("uploads", "products"))
    return {"image_url": f"/uploads/products/{os.path.basename(filepath)}"}


@router.put("/variants/{variant_id}", response_model=schemas.ProductVariantResponse)
def update_variant(variant_id: int, variant_data: schemas.ProductVariantBase, db: Session = Depends(get_db), role: str = Depends(get_current_user_role)):
    if role not in ["ADMIN", "MANAGER"]:
        raise HTTPException(status_code=403, detail="Non autorisé.")
        
    variant = db.query(models.ProductVariant).filter(models.ProductVariant.id == variant_id).first()
    if not variant: raise HTTPException(404, "Variant not found")
    for key, value in variant_data.model_dump().items():
        if key != "quantity_in_stock": setattr(variant, key, value)
    db.commit()
    db.refresh(variant)
    annotate_variant_availability(db, variant)
    return variant

@router.post("/products/{product_id}/variants", response_model=schemas.ProductVariantResponse)
def add_variant(product_id: int, variant_data: schemas.ProductVariantCreate, db: Session = Depends(get_db), role: str = Depends(require_roles("ADMIN", "MANAGER"))):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product: raise HTTPException(404, "Product not found")
    new_variant = models.ProductVariant(product_id=product.id, **variant_data.model_dump())
    db.add(new_variant)
    db.commit()
    db.refresh(new_variant)
    annotate_variant_availability(db, new_variant)
    return new_variant

from fastapi import BackgroundTasks

# ODOO ENGINE: Stock Moves
@router.post("/transaction") # Kept same endpoint name for UI compat momentarily, but treats it as an Odoo Move
def create_transaction(tx: schemas.StockMoveCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    from ..core.events import EventBus
    
    role = user.get("role")
    if role not in ["ADMIN", "MANAGER"]:
        raise HTTPException(status_code=403, detail="Privilèges insuffisants pour créer un mouvement de stock.")
        
    variant = db.query(models.ProductVariant).filter(models.ProductVariant.id == tx.variant_id).first()
    if not variant: raise HTTPException(404, "Variant not found")

    qty = abs(tx.quantity)
    src_loc = db.query(models.StockLocation).filter_by(id=tx.location_id).first() if tx.location_id else None
    dest_loc = db.query(models.StockLocation).filter_by(id=tx.location_dest_id).first() if tx.location_dest_id else None
    is_manual_inventory_adjustment = bool(
        (src_loc and src_loc.usage == "inventory")
        or (dest_loc and dest_loc.usage == "inventory")
    )
    if is_manual_inventory_adjustment and not (tx.reason or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Motif obligatoire pour un ajustement manuel d'inventaire.",
        )
    try:
        result = InventoryService.move_stock(
            db,
            variant_id=tx.variant_id,
            source_location_id=tx.location_id,
            dest_location_id=tx.location_dest_id,
            quantity=qty,
            reference=f"WH/MOVE-{int(time.time()*1000)}",
            notes=tx.notes,
            author=user.get("sub", "Admin"),
            source_screen=tx.source_screen or "stock.manual_transaction",
            document_type=tx.document_type or ("manual_inventory_adjustment" if is_manual_inventory_adjustment else "manual_stock_move"),
            document_reference=tx.document_reference,
            business_reason=tx.reason or tx.notes,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 423 if "Zone gelée" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc

    if (
        src_loc
        and src_loc.usage == 'internal'
        and result.previous_source_quantity is not None
        and result.new_source_quantity is not None
        and result.previous_source_quantity > variant.min_threshold
        and result.new_source_quantity <= variant.min_threshold
    ):
        EventBus.on_stock_alert(variant.reference, result.new_source_quantity, background_tasks)
    
    # --- LOG CHATTER (AUDIT) ---
    src_name = "Externe"
    if tx.location_id:
        src_name = src_loc.name if src_loc else "Inconnu"
        
    dest_name = "Externe"
    if tx.location_dest_id:
        dest_name = dest_loc.name if dest_loc else "Inconnu"

    msg = f"Mouvement de {qty} unité(s): {src_name} ➔ {dest_name} (Mvmt: {result.move.reference})"
    
    # Enrichment for Suppliers / Clients traceability
    variant_db = db.query(models.ProductVariant).filter(models.ProductVariant.id == tx.variant_id).first()
    supplier_name = variant_db.product.supplier if variant_db and variant_db.product and variant_db.product.supplier else "Fournisseur Inconnu"
    
    if tx.location_id and src_loc and src_loc.usage == 'supplier':
        msg += f"\nRéception depuis : {supplier_name}"
    elif tx.location_dest_id and dest_loc and dest_loc.usage == 'customer':
        # Default customer text for manual delivery
        msg += f"\nLivraison vers : Client"

    if tx.notes:
        msg += f"\nNote: {tx.notes}"

    audit_log = models.ChatterMessage(
        model_name="variant",
        record_id=tx.variant_id,
        body=msg,
        author=user.get("sub", "Admin"),
        is_system_log=True
    )
    db.add(audit_log)
    # ---------------------------

    db.commit()
    return {"status": "success"}

@router.get("/transactions")
def get_recent_transactions(db: Session = Depends(get_db)):
    moves = db.query(models.StockMove).options(joinedload(models.StockMove.variant).joinedload(models.ProductVariant.product)).order_by(models.StockMove.date.desc()).limit(100).all()
    result = []
    for m in moves:
        item_name = f"{m.variant.product.name} ({m.variant.color or 'Std'})" if m.variant and m.variant.product else "Inconnu"
        
        # Resolve names for display
        src_name = m.source_location.name if m.source_location else "Fournisseur / Externe"
        dest_name = m.dest_location.name if m.dest_location else "Client / Perte"
        is_workshop_debit = bool(
            (m.reference or "").startswith("DEBIT-ATELIER")
            or "Débit atelier réel" in (m.notes or "")
            or "Consommation réservation" in (m.notes or "")
        )
        
        result.append({
            "id": m.id,
            "reference": m.reference,
            "variant_id": m.variant_id,
            "item_name": item_name,
            "quantity_change": m.quantity,
            "transaction_type": "Débit atelier réel" if is_workshop_debit else f"{src_name} ➔ {dest_name}",
            "movement_kind": "workshop_debit" if is_workshop_debit else "stock_move",
            "created_at": m.date,
            "author": m.author or "Admin",
            "notes": m.notes,
            "source_screen": m.source_screen,
            "document_type": m.document_type,
            "document_reference": m.document_reference,
            "business_reason": m.business_reason,
        })
    return result


@router.get("/transactions/export")
def export_stock_audit_xlsx(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    if user.get("role") not in ["ADMIN", "MANAGER"]:
        raise HTTPException(status_code=403, detail="Seul un manager peut exporter le journal stock.")

    moves = (
        db.query(models.StockMove)
        .options(
            joinedload(models.StockMove.variant).joinedload(models.ProductVariant.product),
            joinedload(models.StockMove.source_location),
            joinedload(models.StockMove.dest_location),
        )
        .order_by(models.StockMove.date.desc())
        .limit(5000)
        .all()
    )
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Audit stock"
    headers = [
        "Date",
        "Reference mouvement",
        "Source ecran",
        "Type document",
        "Reference document",
        "Motif",
        "Auteur",
        "Article",
        "Reference variante",
        "Source",
        "Destination",
        "Quantite",
        "Notes",
    ]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="E2E8F0")

    for move in moves:
        product_name = move.variant.product.name if move.variant and move.variant.product else "Inconnu"
        variant_ref = move.variant.reference if move.variant else ""
        ws.append(
            [
                move.date.strftime("%Y-%m-%d %H:%M:%S") if move.date else "",
                move.reference or "",
                move.source_screen or "",
                move.document_type or "",
                move.document_reference or "",
                move.business_reason or "",
                move.author or "",
                product_name,
                variant_ref,
                move.source_location.name if move.source_location else "Externe",
                move.dest_location.name if move.dest_location else "Externe",
                float(move.quantity or 0),
                move.notes or "",
            ]
        )

    for column_cells in ws.columns:
        max_length = max(len(str(cell.value or "")) for cell in column_cells)
        ws.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 2, 12), 42)

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    response = StreamingResponse(
        iter([stream.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response.headers["Content-Disposition"] = "attachment; filename=stock-audit.xlsx"
    return response

@router.post("/workshop-debits/preview", response_model=schemas.WorkshopDebitPreviewResponse)
async def preview_workshop_debits(
    files: List[UploadFile] = File(...),
    source_location: str = Form("WH/Stock"),
    sale_order_id: Optional[int] = Form(None),
    production_order_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    records, issues, _source_names = await _parse_workshop_uploads(files)
    return build_preview_payload(
        db,
        records,
        issues,
        source_location,
        sale_order_id=sale_order_id,
        production_order_id=production_order_id,
    )

@router.post("/workshop-debits/draft-products")
async def create_draft_products_from_workshop_debits(
    files: List[UploadFile] = File(...),
    source_location: str = Form("WH/Stock"),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    if user.get("role") not in ["ADMIN", "MANAGER"]:
        raise HTTPException(status_code=403, detail="Seul un manager peut créer des brouillons catalogue.")

    records, issues, _source_names = await _parse_workshop_uploads(files)
    if any(issue.severity == "error" for issue in issues):
        raise HTTPException(status_code=400, detail="Fichier de débit non exploitable.")

    preview = build_preview_payload(db, records, issues, source_location)
    unknown_lines = [line for line in preview["stock_matches"] if line["status"] == "not_found"]
    location = db.query(models.StockLocation).filter_by(name=source_location, usage="internal").first()
    if not location:
        location = models.StockLocation(name=source_location, usage="internal", is_active=True)
        db.add(location)
        db.flush()

    created = 0
    skipped = 0
    refs = []
    for line in unknown_lines:
        supplier = (line["supplier"] or "FOURNISSEUR").strip().upper()
        reference = (line["reference"] or "").strip()
        if not reference:
            skipped += 1
            continue
        variant_ref = f"{supplier}:{reference}"
        existing = db.query(models.ProductVariant).filter(models.ProductVariant.reference == variant_ref).first()
        if existing:
            skipped += 1
            continue

        unit = line["unit"] or "unité"
        material_type = "ALU" if supplier in {"SEPALUMIC", "CORTIZO", "TECHNAL/HYDRO", "TECHNAL", "HYDRO"} else "UNKNOWN"
        product = models.Product(
            reference_base=variant_ref,
            name=f"[BROUILLON] {supplier} {reference} - à compléter",
            material_type=material_type,
            unit=unit,
            supplier=supplier,
            product_type="stockable",
            available_in_pos=False,
            compatible_series="Créé depuis prévisualisation débit atelier; stock réel à renseigner.",
            catalog_status="DRAFT",
        )
        db.add(product)
        db.flush()
        variant = models.ProductVariant(
            product_id=product.id,
            reference=variant_ref,
            supplier_reference=reference,
            quantity_in_stock=0,
            min_threshold=0,
            location=source_location,
        )
        db.add(variant)
        db.flush()
        db.add(models.StockQuant(variant_id=variant.id, location_id=location.id, quantity=0))
        created += 1
        refs.append(variant_ref)

    db.commit()
    return {
        "created": created,
        "skipped": skipped,
        "references": refs[:50],
        "message": f"{created} brouillon(s) catalogue créé(s), {skipped} ignoré(s).",
    }

@router.get("/workshop-debits/contexts")
def list_workshop_debit_contexts(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    sales = (
        db.query(models.SaleOrder)
        .filter(models.SaleOrder.status.in_(["SENT", "VALIDATED", "IN_DESIGN", "READY_FOR_PROD", "IN_PRODUCTION"]))
        .order_by(models.SaleOrder.updated_at.desc())
        .limit(100)
        .all()
    )
    active_plans = (
        db.query(models.Planning)
        .options(joinedload(models.Planning.order))
        .filter(
            models.Planning.status.in_([
                models.PlanningStatus.PENDING,
                models.PlanningStatus.IN_PROGRESS,
                models.PlanningStatus.PAUSED,
                models.PlanningStatus.ISSUE,
            ])
        )
        .order_by(models.Planning.created_at.desc())
        .limit(100)
        .all()
    )

    production_orders = []
    seen_order_ids = set()
    for plan in active_plans:
        if not plan.order or plan.order_id in seen_order_ids:
            continue
        seen_order_ids.add(plan.order_id)
        material = plan.order.material.value if hasattr(plan.order.material, "value") else plan.order.material
        production_orders.append(
            {
                "type": "production_order",
                "id": plan.order.id,
                "reference": plan.order.reference,
                "client_name": plan.order.client_name,
                "status": plan.status.value if hasattr(plan.status, "value") else plan.status,
                "material": material,
                "station": plan.station,
                "label": f"{plan.order.reference} - {plan.order.client_name or 'Atelier'} ({material})",
            }
        )

    return {
        "sales": [
            {
                "type": "sale_order",
                "id": sale.id,
                "reference": sale.reference,
                "client_name": sale.client_name,
                "status": sale.status,
                "is_reservable": sale.status in ["VALIDATED", "IN_DESIGN", "READY_FOR_PROD", "IN_PRODUCTION"],
                "label": f"{sale.reference} - {sale.client_name}",
            }
            for sale in sales
        ],
        "production_orders": production_orders,
    }

@router.post("/workshop-debits/reservations", response_model=schemas.StockReservationResponse)
async def reserve_workshop_debits(
    files: List[UploadFile] = File(...),
    source_location: str = Form("WH/Stock"),
    sale_order_id: Optional[int] = Form(None),
    production_order_id: Optional[int] = Form(None),
    order_reference: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    allow_missing: bool = Form(False),
    allow_shortage: bool = Form(False),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    if user.get("role") not in ["ADMIN", "MANAGER"]:
        raise HTTPException(status_code=403, detail="Seul un manager peut réserver un débit atelier.")
    if (allow_missing or allow_shortage) and user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Seul un administrateur peut forcer une réservation incomplète.")
    records, issues, source_names = await _parse_workshop_uploads(files)
    blocking_errors = [issue for issue in issues if issue.severity == "error"]
    if blocking_errors:
        raise HTTPException(status_code=400, detail="Fichier de débit non exploitable.")
    try:
        reservation = create_reservation(
            db,
            records,
            source_label=", ".join(source_names),
            created_by=user.get("sub", "Admin"),
            source_location=source_location,
            order_reference=order_reference,
            sale_order_id=sale_order_id,
            production_order_id=production_order_id,
            notes=notes,
            allow_missing=allow_missing,
            allow_shortage=allow_shortage,
        )
        db.commit()
        db.refresh(reservation)
        return reservation
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

@router.get("/workshop-debits/reservations", response_model=List[schemas.StockReservationResponse])
def list_workshop_reservations(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    query = db.query(models.StockReservation).options(
        joinedload(models.StockReservation.lines).joinedload(models.StockReservationLine.variant)
    ).order_by(models.StockReservation.created_at.desc())
    if status:
        query = query.filter(models.StockReservation.status == status)
    return query.limit(50).all()

@router.post("/workshop-debits/reservations/{reservation_id}/consume")
def consume_workshop_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    if user.get("role") not in ["ADMIN", "MANAGER"]:
        raise HTTPException(status_code=403, detail="Seul un manager peut consommer une réservation atelier.")
    reservation = (
        db.query(models.StockReservation)
        .options(joinedload(models.StockReservation.lines).joinedload(models.StockReservationLine.variant))
        .filter(models.StockReservation.id == reservation_id)
        .first()
    )
    if not reservation:
        raise HTTPException(status_code=404, detail="Réservation introuvable.")
    try:
        stats = consume_reservation(db, reservation, author=user.get("sub", "Admin"))
        db.commit()
        return {"status": "success", **stats}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

@router.post("/workshop-debits/reservations/{reservation_id}/cancel")
def cancel_workshop_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    if user.get("role") not in ["ADMIN", "MANAGER"]:
        raise HTTPException(status_code=403, detail="Seul un manager peut annuler une réservation atelier.")
    reservation = (
        db.query(models.StockReservation)
        .options(joinedload(models.StockReservation.lines))
        .filter(models.StockReservation.id == reservation_id)
        .first()
    )
    if not reservation:
        raise HTTPException(status_code=404, detail="Réservation introuvable.")
    stats = cancel_reservation(db, reservation)
    db.commit()
    return {"status": "success", **stats}

@router.get("/locations", response_model=List[schemas.StockLocationResponse])
def get_locations(db: Session = Depends(get_db)):
    # On renvoie uniquement les emplacements actifs pour cacher les archivés
    return db.query(models.StockLocation).filter(models.StockLocation.is_active == True).all()

@router.post("/locations", response_model=schemas.StockLocationResponse)
def create_location(loc: schemas.StockLocationCreate, db: Session = Depends(get_db), role: str = Depends(get_current_user_role)):
    if role not in ["ADMIN"]:
        raise HTTPException(status_code=403, detail="Seul un Administrateur peut structurer les entrepôts.")
        
    existing = db.query(models.StockLocation).filter(models.StockLocation.name == loc.name).first()
    if existing: raise HTTPException(400, "Location name already exists")
    db_loc = models.StockLocation(**loc.model_dump())
    db.add(db_loc)
    db.commit()
    db.refresh(db_loc)
    return db_loc

@router.put("/locations/{loc_id}", response_model=schemas.StockLocationResponse)
def update_location(loc_id: int, payload: schemas.StockLocationUpdate, db: Session = Depends(get_db), role: str = Depends(get_current_user_role)):
    if role not in ["ADMIN"]:
        raise HTTPException(status_code=403, detail="Seul un Administrateur peut structurer les entrepôts.")

    loc = db.query(models.StockLocation).filter(models.StockLocation.id == loc_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Emplacement introuvable.")

    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Nom d'emplacement obligatoire.")
        existing = (
            db.query(models.StockLocation)
            .filter(models.StockLocation.name == name, models.StockLocation.id != loc_id)
            .first()
        )
        if existing:
            raise HTTPException(status_code=400, detail="Un emplacement porte déjà ce nom.")
        loc.name = name
    if "usage" in data and data["usage"]:
        loc.usage = data["usage"]
    if "parent_id" in data:
        if data["parent_id"] == loc_id:
            raise HTTPException(status_code=400, detail="Un emplacement ne peut pas être son propre parent.")
        loc.parent_id = data["parent_id"]
    if "is_active" in data and data["is_active"] is not None:
        loc.is_active = data["is_active"]

    db.commit()
    db.refresh(loc)
    return loc

@router.delete("/locations/{loc_id}")
def delete_location(loc_id: int, db: Session = Depends(get_db), role: str = Depends(get_current_user_role)):
    if role not in ["ADMIN", "SUPER_ADMIN"]:
        raise HTTPException(status_code=403, detail="Seuls les administrateurs peuvent supprimer ou archiver des emplacements.")

    loc = db.query(models.StockLocation).filter(models.StockLocation.id == loc_id).first()
    if not loc:
        return {"status": "success"}

    # Protection 1 : Les 4 lieux systèmes vitaux
    if loc.usage in ['supplier', 'customer', 'inventory', 'production'] and loc.parent_id is None:
        raise HTTPException(400, f"Action Interdite : Ce lieu virtuel système ({loc.usage}) est vital pour le moteur à partie double.")

    # Protection 2 : Détection de stock vivant dans l'arbre entier
    def check_active_stock(location_id):
        active_quants = db.query(models.StockQuant).filter(
            models.StockQuant.location_id == location_id, 
            models.StockQuant.quantity > 0
        ).count()
        if active_quants > 0: return True
        
        children = db.query(models.StockLocation).filter(models.StockLocation.parent_id == location_id).all()
        for child in children:
            if check_active_stock(child.id): return True
        return False

    if check_active_stock(loc_id):
        raise HTTPException(400, "Action Interdite : Cet emplacement (ou une de ses étagères) contient du stock actif. Transférez le stock avant la suppression/archivage.")

    # Get all descendants
    def get_all_descendants(location_id):
        children = db.query(models.StockLocation).filter(models.StockLocation.parent_id == location_id).all()
        descendants = [c.id for c in children]
        for c in children:
            descendants.extend(get_all_descendants(c.id))
        return descendants
        
    all_loc_ids = [loc_id] + get_all_descendants(loc_id)

    # Protection 3 : Archivage au lieu de suppression s'il y a un historique dans l'arbre
    historical_moves = db.query(models.StockMove).filter(
        or_(
            models.StockMove.location_id.in_(all_loc_ids),
            models.StockMove.location_dest_id.in_(all_loc_ids)
        )
    ).count()

    if historical_moves > 0:
        # On archive tout l'arbre
        db.query(models.StockLocation).filter(models.StockLocation.id.in_(all_loc_ids)).update({"is_active": False}, synchronize_session=False)
        db.commit()
        return {"status": "archived"}
    else:
        # On supprime physiquement les Quants vides pour éviter une IntegrityError
        db.query(models.StockQuant).filter(models.StockQuant.location_id.in_(all_loc_ids)).delete(synchronize_session=False)
        db.delete(loc)
        db.commit()
        return {"status": "deleted"}

@router.get("/quants", response_model=List[schemas.StockQuantResponse])
def get_all_quants(db: Session = Depends(get_db)):
    # Renvoie tous les quants dont la quantité est > 0 pour l'affichage Odoo
    return db.query(models.StockQuant).filter(models.StockQuant.quantity > 0).all()

# --- CHATTER (AUDIT LOG) CHANNELS ---

@router.get("/chatter/{model_name}/{record_id}", response_model=List[schemas.ChatterMessageResponse])
def get_chatter(model_name: str, record_id: int, db: Session = Depends(get_db)):
    return db.query(models.ChatterMessage).filter(
        models.ChatterMessage.model_name == model_name,
        models.ChatterMessage.record_id == record_id
    ).order_by(models.ChatterMessage.created_at.desc()).all()

@router.post("/chatter", response_model=schemas.ChatterMessageResponse)
def post_chatter_message(msg: schemas.ChatterMessageCreate, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    db_msg = models.ChatterMessage(
        model_name=msg.model_name,
        record_id=msg.record_id,
        body=msg.body,
        author=user.get("sub", "User"),
        is_system_log=msg.is_system_log
    )
    db.add(db_msg)
    db.commit()
    db.refresh(db_msg)
    return db_msg

# --- BULK IMPORT / EXPORT EXCEL ---

@router.get("/import/template")
def get_import_template():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Import_PIM"
    headers = [
        "Reference_Parent", "Nom_Famille", "Matiere", "Unite", "Fournisseur", "Type_Article",
        "Visible_Vente_PDV", "Image_Lien", "Fiche_Tech_Lien", "Gammes_Compatibles", "Reference_Variante", "Code_Barre", "Specificites_Couleur",
        "Prix_Achat", "Seuil_Alerte", "Chemin_Rangement"
    ]
    ws.append(headers)
    for col in range(1, len(headers) + 1):
        ws.cell(row=1, column=col).font = Font(bold=True, color="FFFFFF")
        ws.cell(row=1, column=col).fill = PatternFill(start_color="333333", fill_type="solid")
    
    # Une ligne d'exemple
    ws.append([
        "3186", "Double poignée de porte Cortizo", "QUINCAILLERIE", "pce", "CORTIZO", "stockable",
        "0", "", "COR 60, COR 70", "318601", "340001000211", "Blanc",
        25.50, 10, "A1-R3-B"
    ])
    
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    response = StreamingResponse(iter([stream.getvalue()]), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response.headers["Content-Disposition"] = "attachment; filename=MMG_Template_Import_Produits.xlsx"
    return response

@router.post("/import/upload")
async def upload_import_file(file: UploadFile = File(...), db: Session = Depends(get_db), role: str = Depends(get_current_user_role)):
    if role not in ["ADMIN", "MANAGER"]:
        raise HTTPException(status_code=403, detail="Import de masse réservé aux managers.")
        
    if not file.filename.endswith('.xlsx'):
        raise HTTPException(400, "Le fichier doit être un .xlsx")

    content = await file.read()
    stream = io.BytesIO(content)
    
    try:
        wb = openpyxl.load_workbook(stream, data_only=True)
        ws = wb.active
    except Exception as e:
        raise HTTPException(400, "Impossible de lire le fichier Excel.")
        
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 1:
        raise HTTPException(400, "Le fichier est vide.")
        
    headers = [str(h).strip() if h else "" for h in rows[0]]
    required_cols = {"Reference_Parent", "Nom_Famille", "Reference_Variante"}
    
    if not required_cols.issubset(set(headers)):
        raise HTTPException(400, f"Colonnes manquantes. Requis : {', '.join(required_cols)}")
        
    created_products = 0
    created_variants = 0
    
    # Convert header to row dict mapping
    for i in range(1, len(rows)):
        row_vals = rows[i]
        # Ignore empty rows
        if not any(row_vals):
            continue
            
        row = dict(zip(headers, row_vals))
        
        ref_parent = str(row.get("Reference_Parent") or "").strip()
        nom = str(row.get("Nom_Famille") or "").strip()
        ref_var = str(row.get("Reference_Variante") or "").strip()
        
        if not ref_parent or not nom or not ref_var:
            continue
            
        # 1. Chercher ou créer le Product (Parent)
        product = db.query(models.Product).filter(models.Product.reference_base == ref_parent).first()
        image_url = str(row.get("Image_Lien") or "").strip()
        
        if not product:
            product = models.Product(
                reference_base=ref_parent,
                name=nom,
                material_type=str(row.get("Matiere") or "INCONNU"),
                unit=str(row.get("Unite") or "pce"),
                supplier=str(row.get("Fournisseur") or ""),
                product_type=str(row.get("Type_Article") or "stockable"),
                available_in_pos=True if str(row.get("Visible_Vente_PDV") or "") in ["1", "true", "oui", "OUI", "True", 1] else False,
                image_url=image_url if image_url else None,
                technical_doc_url=str(row.get("Fiche_Tech_Lien") or "").strip() or None,
                compatible_series=str(row.get("Gammes_Compatibles") or "").strip()
            )
            db.add(product)
            db.flush() # get product.id
            created_products += 1
        elif image_url and not product.image_url:
            product.image_url = image_url # Update if provided and missing
            
        # 2. Créer la Variante (Enfant)
        variant = db.query(models.ProductVariant).filter(models.ProductVariant.reference == ref_var).first()
        if not variant:
            code_barre = str(row.get("Code_Barre") or "").strip()
            
            try:
                cp = float(row.get("Prix_Achat") or 0)
            except:
                cp = 0
            
            try:    
                mt = float(row.get("Seuil_Alerte") or 10)
            except:
                mt = 10
                
            variant = models.ProductVariant(
                product_id=product.id,
                reference=ref_var,
                barcode=code_barre if code_barre else None,
                color=str(row.get("Specificites_Couleur") or ""),
                cost_price=cp,
                min_threshold=mt,
                location=str(row.get("Chemin_Rangement") or "").strip()
            )
            db.add(variant)
            created_variants += 1
            
    db.commit()
    return {"message": f"Import réussi : {created_products} familles créées, {created_variants} déclinaisons ajoutées."}

@router.get("/export/inventory")
def export_inventory_xlsx(db: Session = Depends(get_db)):
    from sqlalchemy.orm import joinedload
    # Document comptable : seul le stock physiquement détenu (emplacements
    # internes actifs) est exporté. Les emplacements virtuels `customer`
    # (cumul des ventes), `inventory` (pertes/écarts) et `supplier` sont
    # exclus — sinon la valorisation additionne stock réel + vendu + pertes.
    quants = (
        db.query(models.StockQuant)
        .join(models.StockLocation, models.StockQuant.location_id == models.StockLocation.id)
        .options(
            joinedload(models.StockQuant.variant).joinedload(models.ProductVariant.product),
            joinedload(models.StockQuant.location)
        )
        .filter(
            models.StockLocation.usage == "internal",
            models.StockLocation.is_active == True,
        )
        .all()
    )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Inventaire_Interne_MMG"
    headers = [
        "Lieu / Magasin (stock interne)", "Reference", "Designation", "Code Barre", "Type",
        "Quantite", "Unite", "Prix Unitaire", "Valeur Totale"
    ]
    ws.append(headers)
    for col in range(1, len(headers) + 1):
        ws.cell(row=1, column=col).font = Font(bold=True, color="FFFFFF")
        ws.cell(row=1, column=col).fill = PatternFill(start_color="1E3A8A", fill_type="solid")
        
    for q in quants:
        v = q.variant
        p = v.product if v else None
        loc = q.location
        if not v or not p or not loc:
            continue
            
        valeur_totale = float(q.quantity) * float(v.cost_price or 0)
        ws.append([
            loc.name,
            v.reference,
            f"{p.name} ({v.color or 'Std'})",
            v.barcode or "",
            p.product_type,
            q.quantity,
            p.unit,
            float(v.cost_price or 0),
            valeur_totale
        ])
    
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    
    response = StreamingResponse(iter([stream.getvalue()]), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response.headers["Content-Disposition"] = "attachment; filename=MMG_Inventaire_Actuel.xlsx"
    return response

@router.get("/catalog/drafts/export")
def export_draft_catalog_xlsx(db: Session = Depends(get_db)):
    drafts = (
        db.query(models.Product)
        .options(joinedload(models.Product.variants))
        .filter(models.Product.catalog_status == "DRAFT")
        .order_by(models.Product.supplier.asc(), models.Product.reference_base.asc())
        .all()
    )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Brouillons_Catalogue"
    headers = [
        "Reference_Parent",
        "Reference_Variante",
        "Fournisseur",
        "Nom_Famille",
        "Matiere",
        "Unite",
        "Ref_Fournisseur",
        "Longueur_Unite",
        "Emplacement",
        "Gammes_Compatibles",
        "Statut_Catalogue",
        "Commentaire",
    ]
    ws.append(headers)
    for col in range(1, len(headers) + 1):
        ws.cell(row=1, column=col).font = Font(bold=True, color="FFFFFF")
        ws.cell(row=1, column=col).fill = PatternFill(start_color="D97706", fill_type="solid")

    for product in drafts:
        variants = product.variants or [None]
        for variant in variants:
            ws.append(
                [
                    product.reference_base,
                    variant.reference if variant else "",
                    product.supplier or "",
                    product.name,
                    product.material_type,
                    product.unit,
                    variant.supplier_reference if variant else "",
                    variant.length_per_unit if variant else "",
                    variant.location if variant else "",
                    product.compatible_series or "",
                    product.catalog_status or "DRAFT",
                    "",
                ]
            )

    for column_cells in ws.columns:
        max_length = max(len(str(cell.value or "")) for cell in column_cells)
        ws.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 2, 14), 45)

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    response = StreamingResponse(iter([stream.getvalue()]), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response.headers["Content-Disposition"] = "attachment; filename=MMG_Brouillons_Catalogue.xlsx"
    return response

@router.post("/catalog/drafts/import")
async def import_draft_catalog_updates(file: UploadFile = File(...), db: Session = Depends(get_db), role: str = Depends(get_current_user_role)):
    if role not in ["ADMIN", "MANAGER"]:
        raise HTTPException(status_code=403, detail="Import brouillons réservé aux managers.")
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Le fichier doit être un .xlsx")

    try:
        wb = openpyxl.load_workbook(io.BytesIO(await file.read()), data_only=True)
        ws = wb.active
    except Exception:
        raise HTTPException(status_code=400, detail="Impossible de lire le fichier Excel.")

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise HTTPException(status_code=400, detail="Le fichier est vide.")

    headers = [str(h).strip() if h else "" for h in rows[0]]
    required = {"Reference_Parent", "Reference_Variante"}
    if not required.issubset(set(headers)):
        raise HTTPException(status_code=400, detail=f"Colonnes manquantes. Requis : {', '.join(sorted(required))}")

    updated_products = 0
    updated_variants = 0
    skipped = 0
    active_values = {"ACTIVE", "ACTIF", "1", "TRUE", "OUI", "YES"}

    for values in rows[1:]:
        if not any(values):
            continue
        row = dict(zip(headers, values))
        ref_parent = str(row.get("Reference_Parent") or "").strip()
        ref_variant = str(row.get("Reference_Variante") or "").strip()
        if not ref_parent and not ref_variant:
            skipped += 1
            continue

        product = db.query(models.Product).filter(models.Product.reference_base == ref_parent).first() if ref_parent else None
        variant = db.query(models.ProductVariant).filter(models.ProductVariant.reference == ref_variant).first() if ref_variant else None
        if not product and variant:
            product = variant.product
        if not product:
            skipped += 1
            continue

        def text_value(key: str):
            value = row.get(key)
            return str(value).strip() if value is not None else None

        for key, attr in [
            ("Nom_Famille", "name"),
            ("Matiere", "material_type"),
            ("Unite", "unit"),
            ("Fournisseur", "supplier"),
            ("Gammes_Compatibles", "compatible_series"),
        ]:
            value = text_value(key)
            if value:
                setattr(product, attr, value)

        status = text_value("Statut_Catalogue")
        if status:
            product.catalog_status = "ACTIVE" if status.upper() in active_values else "DRAFT"
        updated_products += 1

        if variant:
            supplier_ref = text_value("Ref_Fournisseur")
            location = text_value("Emplacement")
            if supplier_ref:
                variant.supplier_reference = supplier_ref
            if location:
                variant.location = location
            length = row.get("Longueur_Unite")
            if length not in (None, ""):
                try:
                    variant.length_per_unit = float(length)
                except (TypeError, ValueError):
                    pass
            updated_variants += 1

    db.commit()
    return {
        "message": f"Mise à jour brouillons : {updated_products} famille(s), {updated_variants} variante(s), {skipped} ligne(s) ignorée(s).",
        "updated_products": updated_products,
        "updated_variants": updated_variants,
        "skipped": skipped,
    }

@router.post("/import-bom/{sale_order_id}")
async def import_bom_for_sale_order(sale_order_id: int, background_tasks: BackgroundTasks, file: UploadFile = File(...), db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    from ..core.events import EventBus
    
    if user.get("role") not in ["ADMIN", "MANAGER"]:
        raise HTTPException(status_code=403, detail="Seul le BE ou un Manager peut importer une nomenclature.")
        
    sale = db.query(models.SaleOrder).filter(models.SaleOrder.id == sale_order_id).first()
    if not sale:
        raise HTTPException(404, "Sale Order introuvable")

    contents = await file.read()
    try:
        content_str = contents.decode("utf-8")
    except UnicodeDecodeError:
        content_str = contents.decode("latin-1")

    bom_items = parse_bom_file(content_str, file.filename)
    if not bom_items:
        raise HTTPException(400, "Le fichier est vide ou le format n'est pas reconnu.")

    prod_loc = InventoryService.get_or_create_location(db, "Production Ateliers", "production")

    wh_loc = db.query(models.StockLocation).filter(models.StockLocation.usage == "internal").first()
    if not wh_loc:
        raise HTTPException(400, "Aucun entrepôt physique trouvé.")

    processed_count = 0
    not_found_refs = []
    stock_warnings = []

    for item in bom_items:
        ref = item["reference"]
        qty = item["quantity"]
        
        variant = db.query(models.ProductVariant).filter(or_(
            models.ProductVariant.reference == ref,
            models.ProductVariant.barcode == ref,
            models.ProductVariant.supplier_reference == ref
        )).first()

        if not variant:
            not_found_refs.append(ref)
            continue
            
        src_quant = db.query(models.StockQuant).filter_by(variant_id=variant.id, location_id=wh_loc.id).first()
        current_source_qty = float(src_quant.quantity if src_quant else 0)

        # Check for stock warnings (Non-blocking)
        if current_source_qty < qty:
            shortage = qty - current_source_qty
            stock_warnings.append(f"{variant.reference} : manque {shortage} {variant.product.unit if variant.product else 'unités'} en stock.")

        try:
            result = InventoryService.move_stock(
                db,
                variant_id=variant.id,
                source_location_id=wh_loc.id,
                dest_location_id=prod_loc.id,
                quantity=qty,
                reference=f"PROD-{sale.reference}-BOM",
                notes=f"Débit BOM auto ({file.filename})",
                author="Système / Admin",
                source_screen="stock.legacy_bom_import",
                document_type="sale_order",
                document_reference=sale.reference,
                business_reason="Import BOM historique vers production",
                allow_negative_source=True,
            )
        except ValueError as exc:
            status_code = 423 if "Zone gelée" in str(exc) else 400
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

        if (
            result.previous_source_quantity is not None
            and result.new_source_quantity is not None
            and result.previous_source_quantity > variant.min_threshold
            and result.new_source_quantity <= variant.min_threshold
        ):
            EventBus.on_stock_alert(variant.reference, result.new_source_quantity, background_tasks)
        
        # Log to Chatter
        audit_log = models.ChatterMessage(
            model_name="variant",
            record_id=variant.id,
            body=f"Consommation pour Commande {sale.reference} (Nomenclature {file.filename}). Quantité réservée : {qty}",
            author=user.get("sub", "BE / Admin"),
            is_system_log=True
        )
        db.add(audit_log)
        
        processed_count += 1
        
    sale.status = "READY_FOR_PROD"
    if stock_warnings:
        sale.notes = (sale.notes or "") + f"\n[ALERTE STOCK] {len(stock_warnings)} ruptures potentielles au lancement."
        
    db.commit()

    return {
        "status": "success", 
        "processed_count": processed_count, 
        "not_found": not_found_refs,
        "warnings": stock_warnings
    }

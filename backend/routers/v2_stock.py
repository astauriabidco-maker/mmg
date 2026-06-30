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
import openpyxl
from openpyxl.styles import Font, PatternFill
from sqlalchemy import or_
from ..services.bom_parser import parse_bom_file
from ..services.stock_reservations import (
    build_preview_payload,
    cancel_reservation,
    consume_reservation,
    create_reservation,
)
from scripts.import_workshop_debits import parse_file

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

@router.get("/products", response_model=List[schemas.ProductResponse])
def get_products(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    return db.query(models.Product).all()

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

@router.post("/products/upload_image")
async def upload_product_image(file: UploadFile = File(...), role: str = Depends(get_current_user_role)):
    if role not in ["ADMIN", "MANAGER"]:
        raise HTTPException(status_code=403, detail="Non autorisé.")
        
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    file_ext = os.path.splitext(file.filename)[1]
    new_filename = f"{uuid.uuid4().hex}{file_ext}"
    filepath = os.path.join("uploads", "products", new_filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    return {"image_url": f"/uploads/products/{new_filename}"}


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
    return variant

@router.post("/products/{product_id}/variants", response_model=schemas.ProductVariantResponse)
def add_variant(product_id: int, variant_data: schemas.ProductVariantCreate, db: Session = Depends(get_db), role: str = Depends(require_roles("ADMIN", "MANAGER"))):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product: raise HTTPException(404, "Product not found")
    new_variant = models.ProductVariant(product_id=product.id, **variant_data.model_dump())
    db.add(new_variant)
    db.commit()
    db.refresh(new_variant)
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
    is_in = tx.quantity > 0
    
    # 1. Update source quant
    if tx.location_id:
        src_quant = db.query(models.StockQuant).filter_by(variant_id=tx.variant_id, location_id=tx.location_id).first()
        if not src_quant:
            src_quant = models.StockQuant(variant_id=tx.variant_id, location_id=tx.location_id, quantity=0)
            db.add(src_quant)
            
        previous_qty = src_quant.quantity
        src_quant.quantity -= qty
        
        # --- INTERNAL AUTOMATION TRIGGER ---
        if previous_qty > variant.min_threshold and src_quant.quantity <= variant.min_threshold:
            EventBus.on_stock_alert(variant.reference, src_quant.quantity, background_tasks)
        src_loc = db.query(models.StockLocation).filter_by(id=tx.location_id).first()
        if src_loc and src_loc.usage == 'internal': pass # Stock total is dynamic now

    # 2. Update dest quant
    if tx.location_dest_id:
        dest_quant = db.query(models.StockQuant).filter_by(variant_id=tx.variant_id, location_id=tx.location_dest_id).first()
        if not dest_quant:
            dest_quant = models.StockQuant(variant_id=tx.variant_id, location_id=tx.location_dest_id, quantity=0)
            db.add(dest_quant)
        dest_quant.quantity += qty
        dest_loc = db.query(models.StockLocation).filter_by(id=tx.location_dest_id).first()
        if dest_loc and dest_loc.usage == 'internal': pass # Stock total is dynamic now

    new_move = models.StockMove(
        reference=f"WH/MOVE-{int(time.time()*1000)}",
        variant_id=tx.variant_id,
        location_id=tx.location_id,
        location_dest_id=tx.location_dest_id,
        quantity=qty,
        notes=tx.notes,
        author=user.get("sub", "Admin")
    )
    db.add(new_move)
    
    # --- LOG CHATTER (AUDIT) ---
    src_name = "Externe"
    if tx.location_id:
        src_loc = db.query(models.StockLocation).filter_by(id=tx.location_id).first()
        src_name = src_loc.name if src_loc else "Inconnu"
        
    dest_name = "Externe"
    if tx.location_dest_id:
        dest_loc = db.query(models.StockLocation).filter_by(id=tx.location_dest_id).first()
        dest_name = dest_loc.name if dest_loc else "Inconnu"

    msg = f"Mouvement de {qty} unité(s): {src_name} ➔ {dest_name} (Mvmt: {new_move.reference})"
    
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
            "notes": m.notes
        })
    return result

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
    quants = db.query(models.StockQuant).options(
        joinedload(models.StockQuant.variant).joinedload(models.ProductVariant.product),
        joinedload(models.StockQuant.location)
    ).all()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Inventaire_MMG"
    headers = [
        "Lieu / Magasin", "Reference", "Designation", "Code Barre", "Type", 
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

    prod_loc = db.query(models.StockLocation).filter(models.StockLocation.name == "Production Ateliers", models.StockLocation.usage == "production").first()
    if not prod_loc:
        prod_loc = models.StockLocation(name="Production Ateliers", usage="production", type="virtual")
        db.add(prod_loc)
        db.flush()

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
        if not src_quant:
            src_quant = models.StockQuant(variant_id=variant.id, location_id=wh_loc.id, quantity=0)
            db.add(src_quant)
            
        dest_quant = db.query(models.StockQuant).filter_by(variant_id=variant.id, location_id=prod_loc.id).first()
        if not dest_quant:
            dest_quant = models.StockQuant(variant_id=variant.id, location_id=prod_loc.id, quantity=0)
            db.add(dest_quant)

        # Check for stock warnings (Non-blocking)
        if src_quant.quantity < qty:
            shortage = qty - src_quant.quantity
            stock_warnings.append(f"{variant.reference} : manque {shortage} {variant.product.unit if variant.product else 'unités'} en stock.")

        previous_qty = src_quant.quantity
        src_quant.quantity -= qty
        
        # --- INTERNAL AUTOMATION TRIGGER ---
        if previous_qty > variant.min_threshold and src_quant.quantity <= variant.min_threshold:
            EventBus.on_stock_alert(variant.reference, src_quant.quantity, background_tasks)
        dest_quant.quantity += qty

        new_move = models.StockMove(
            reference=f"PROD-{sale.reference}-BOM",
            variant_id=variant.id,
            location_id=wh_loc.id,
            location_dest_id=prod_loc.id,
            quantity=qty,
            notes=f"Débit BOM auto ({file.filename})",
            author="Système / Admin"
        )
        db.add(new_move)
        
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

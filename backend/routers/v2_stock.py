from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from .. import models, schemas
from ..core.security import get_current_user, get_current_user_role, require_roles
import time
import io
import openpyxl
from openpyxl.styles import Font, PatternFill
from sqlalchemy import or_
from ..services.bom_parser import parse_bom_file

router = APIRouter(prefix="/v2/stock", tags=["stock"])

@router.get("/products", response_model=List[schemas.ProductResponse])
def get_products(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    return db.query(models.Product).all()

@router.post("/products", response_model=schemas.ProductResponse)
def create_product(product_data: schemas.ProductCreate, db: Session = Depends(get_db), role: str = Depends(get_current_user_role)):
    if role not in ["ADMIN", "MANAGER"]:
        raise HTTPException(status_code=403, detail="Seul un manager peut créer des produits.")
    
    existing = db.query(models.Product).filter(models.Product.reference_base == product_data.reference_base).first()
    if existing: raise HTTPException(400, "Base reference already exists")
    
    new_product = models.Product(**product_data.dict(exclude={'variants'}))
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    
    for v_data in product_data.variants:
        new_variant = models.ProductVariant(product_id=new_product.id, **v_data.dict())
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
    for key, value in product_data.dict().items(): setattr(product, key, value)
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
    for key, value in variant_data.dict().items():
        if key != "quantity_in_stock": setattr(variant, key, value)
    db.commit()
    db.refresh(variant)
    return variant

@router.post("/products/{product_id}/variants", response_model=schemas.ProductVariantResponse)
def add_variant(product_id: int, variant_data: schemas.ProductVariantCreate, db: Session = Depends(get_db), role: str = Depends(require_roles("ADMIN", "MANAGER"))):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product: raise HTTPException(404, "Product not found")
    new_variant = models.ProductVariant(product_id=product.id, **variant_data.dict())
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
    from sqlalchemy.orm import joinedload
    moves = db.query(models.StockMove).options(joinedload(models.StockMove.variant).joinedload(models.ProductVariant.product)).order_by(models.StockMove.date.desc()).limit(100).all()
    result = []
    for m in moves:
        item_name = f"{m.variant.product.name} ({m.variant.color or 'Std'})" if m.variant and m.variant.product else "Inconnu"
        
        # Resolve names for display
        src_name = m.source_location.name if m.source_location else "Fournisseur / Externe"
        dest_name = m.dest_location.name if m.dest_location else "Client / Perte"
        
        result.append({
            "id": m.id,
            "reference": m.reference,
            "item_name": item_name,
            "quantity_change": m.quantity,
            "transaction_type": f"{src_name} ➔ {dest_name}",
            "created_at": m.date,
            "author": m.author or "Admin",
            "notes": m.notes
        })
    return result

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
    db_loc = models.StockLocation(**loc.dict())
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

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Tuple
import tempfile
from pathlib import Path
import json
import os

from ..database import get_db
from .. import models, schemas
from ..core.security import get_current_user
from ..services.stock_reservations import (
    annotate_sale_availability,
    build_preview_payload,
    cancel_reservation,
    consume_commercial_reservation,
    create_commercial_reservation_for_sale,
    create_reservation,
)
from scripts.import_workshop_debits import parse_file

import io
from .v2_accounting import generate_invoice_reference, compute_qr_seal

router = APIRouter(
    prefix="/v2/sales",
    tags=["sales_v2"],
    responses={404: {"description": "Non trouvé"}}
)

AUTH_DEPENDENCIES = [Depends(get_current_user)]
SALE_WORKFLOW_TYPES = {"FREE_SALE", "FABRICATION_ESTIMATE", "FABRICATION_FROM_MEASURE"}
SALE_LINE_TYPES = {"STOCK_ITEM", "SERVICE"}


def _normalise_sale_workflow_type(value: Optional[str]) -> str:
    workflow_type = (value or "FREE_SALE").upper()
    if workflow_type not in SALE_WORKFLOW_TYPES:
        raise HTTPException(status_code=400, detail="Type de devis invalide.")
    return workflow_type


def _normalise_sale_line_type(value: Optional[str], variant_id: Optional[int]) -> str:
    line_type = (value or ("STOCK_ITEM" if variant_id else "SERVICE")).upper()
    aliases = {
        "STOCK": "STOCK_ITEM",
        "ARTICLE": "STOCK_ITEM",
        "PRODUCT": "STOCK_ITEM",
        "PRESTATION": "SERVICE",
        "CUSTOM": "SERVICE",
        "FREE_TEXT": "SERVICE",
    }
    line_type = aliases.get(line_type, line_type)
    if line_type not in SALE_LINE_TYPES:
        raise HTTPException(status_code=400, detail="Type de ligne de devis invalide.")
    return line_type


def _catalog_value_is_inactive(value) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value is False
    return str(value).upper() in {"DRAFT", "INACTIVE", "ARCHIVED", "DISABLED", "FALSE", "0"}


def _ensure_catalog_variant_usable(variant: models.ProductVariant, line_type: str) -> None:
    product = variant.product
    if not product:
        raise HTTPException(status_code=400, detail="Variante catalogue sans produit parent.")

    if _catalog_value_is_inactive(getattr(product, "catalog_status", None)):
        raise HTTPException(status_code=400, detail=f"Produit catalogue non actif: {product.reference_base}.")
    for record in (product, variant):
        if hasattr(record, "is_active") and _catalog_value_is_inactive(getattr(record, "is_active")):
            raise HTTPException(status_code=400, detail="Produit catalogue inactif.")

    product_type = (product.product_type or "").lower()
    if line_type == "STOCK_ITEM" and product_type == "service":
        raise HTTPException(status_code=400, detail="Une ligne STOCK_ITEM doit pointer vers un article stockable.")
    if line_type == "SERVICE" and product_type in {"stockable", "consumable"}:
        raise HTTPException(status_code=400, detail="Une prestation SERVICE ne doit pas pointer vers un article stockable.")


def _resolve_sale_line(db: Session, line_req: schemas.SaleOrderLineCreate) -> Tuple[str, Optional[models.ProductVariant]]:
    line_type = _normalise_sale_line_type(line_req.line_type, line_req.variant_id)
    if line_req.quantity <= 0:
        raise HTTPException(status_code=400, detail="La quantité d'une ligne de devis doit être positive.")
    if line_req.discount_pct < 0 or line_req.discount_pct > 100:
        raise HTTPException(status_code=400, detail="La remise d'une ligne doit être comprise entre 0 et 100%.")
    if line_type == "STOCK_ITEM" and line_req.unit_price <= 0:
        raise HTTPException(status_code=400, detail="Un article stock doit avoir un prix de vente HT positif avant création du devis.")

    variant = None
    if line_type == "STOCK_ITEM" and not line_req.variant_id:
        raise HTTPException(status_code=400, detail="Une ligne STOCK_ITEM doit référencer une variante de stock.")
    if line_req.variant_id:
        variant = (
            db.query(models.ProductVariant)
            .options(joinedload(models.ProductVariant.product))
            .filter(models.ProductVariant.id == line_req.variant_id)
            .first()
        )
        if not variant:
            raise HTTPException(status_code=400, detail=f"Variante introuvable: {line_req.variant_id}.")
        _ensure_catalog_variant_usable(variant, line_type)
    return line_type, variant


def _sale_total_amount(sale: models.SaleOrder) -> float:
    return float(
        sum(
            (line.quantity or 0) * (line.unit_price or 0) * (1 - (line.discount_pct or 0) / 100)
            for line in sale.lines
        )
    )


def _ensure_sale_is_commercially_signable(sale: models.SaleOrder) -> None:
    zero_priced_stock_lines = [
        line.description or f"Ligne #{line.id}"
        for line in sale.lines or []
        if (line.line_type or "").upper() == "STOCK_ITEM" and (line.unit_price or 0) <= 0
    ]
    if zero_priced_stock_lines:
        raise HTTPException(
            status_code=400,
            detail=(
                "Signature impossible: article stock sans prix de vente HT positif. "
                + ", ".join(zero_priced_stock_lines[:5])
            ),
        )


def _load_sale(db: Session, order_id: int) -> Optional[models.SaleOrder]:
    return (
        db.query(models.SaleOrder)
        .options(
            joinedload(models.SaleOrder.lines)
            .joinedload(models.SaleOrderLine.variant)
            .joinedload(models.ProductVariant.product),
            joinedload(models.SaleOrder.mmg_dossiers),
        )
        .filter(models.SaleOrder.id == order_id)
        .first()
    )


def _attach_sale_traceability(db: Session, sale: models.SaleOrder) -> models.SaleOrder:
    sale.reservations = (
        db.query(models.StockReservation)
        .options(
            joinedload(models.StockReservation.lines)
            .joinedload(models.StockReservationLine.variant)
            .joinedload(models.ProductVariant.product)
        )
        .filter(models.StockReservation.sale_order_id == sale.id)
        .order_by(models.StockReservation.created_at.desc())
        .all()
    )
    sale.invoices = (
        db.query(models.Invoice)
        .filter(models.Invoice.sale_order_id == sale.id)
        .order_by(models.Invoice.issue_date.desc())
        .all()
    )
    sale.delivery_notes = (
        db.query(models.DeliveryNote)
        .filter(models.DeliveryNote.sale_order_id == sale.id)
        .order_by(models.DeliveryNote.id.desc())
        .all()
    )
    return sale


def _generate_delivery_note_reference(db: Session) -> str:
    year = datetime.utcnow().year
    count = db.query(models.DeliveryNote).filter(models.DeliveryNote.reference.like(f"BL-{year}-%")).count()
    return f"BL-{year}-{count + 1:04d}"


def _create_commercial_reservation_if_validated(
    db: Session,
    sale: models.SaleOrder,
    actor: str = "Système",
) -> Optional[models.StockReservation]:
    if sale.workflow_type != "FREE_SALE" or sale.status not in {"VALIDATED", "ACCEPTED"}:
        return None
    return create_commercial_reservation_for_sale(db, sale, created_by=actor)


def _cancel_commercial_reservations_for_sale(db: Session, sale: models.SaleOrder) -> int:
    reservations = (
        db.query(models.StockReservation)
        .filter(
            models.StockReservation.sale_order_id == sale.id,
            models.StockReservation.status == "reserved",
            models.StockReservation.source_label.in_(["devis libre", "devis_libre"]),
        )
        .all()
    )
    for reservation in reservations:
        cancel_reservation(db, reservation)
    return len(reservations)


def _sale_has_measure_context(sale: models.SaleOrder) -> bool:
    return bool(sale.mmg_dossiers)


def _ensure_sale_can_prepare_workshop(
    sale: models.SaleOrder,
    allowed_statuses: Optional[set[str]] = None,
) -> None:
    workflow_type = _normalise_sale_workflow_type(getattr(sale, "workflow_type", None))
    if workflow_type == "FREE_SALE":
        raise HTTPException(
            status_code=400,
            detail="Un devis libre pièces/prestations ne peut pas être préparé pour l'atelier fabrication.",
        )
    if workflow_type == "FABRICATION_ESTIMATE" and not _sale_has_measure_context(sale):
        raise HTTPException(
            status_code=400,
            detail="Un pré-devis fabrication doit être rattaché à un métré avant préparation atelier.",
        )
    if allowed_statuses and sale.status not in allowed_statuses:
        readable_statuses = ", ".join(sorted(allowed_statuses))
        raise HTTPException(
            status_code=400,
            detail=f"Préparation atelier autorisée uniquement pour les statuts: {readable_statuses}.",
        )

def _material_from_text(value: Optional[str]) -> Optional[str]:
    text = (value or "").upper()
    if "PVC" in text:
        return "PVC"
    if any(token in text for token in ["ALU", "ALUMINIUM", "CORTIZO", "SEPALUMIC", "TECHNAL"]):
        return "ALU"
    return None

def _material_from_value(value) -> Optional[str]:
    if value is None:
        return None
    raw = value.value if hasattr(value, "value") else str(value)
    return raw if raw in {"ALU", "PVC"} else None

def _line_visual_spec(line: models.SaleOrderLine) -> Optional[Dict]:
    if not line.visual_config:
        return None
    try:
        config = json.loads(line.visual_config)
    except (TypeError, json.JSONDecodeError):
        return None
    width = config.get("width") or config.get("width_mm")
    height = config.get("height") or config.get("height_mm")
    try:
        width = float(width)
        height = float(height)
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    material = _material_from_value(config.get("material")) or _material_from_text(line.description) or "ALU"
    return {
        "source": "sale_line",
        "sale_order_line_id": line.id,
        "reference_suffix": f"L{line.id}",
        "width": width,
        "height": height,
        "material": material,
        "quantity": max(int(line.quantity or 1), 1),
        "system_type": config.get("type") or config.get("opening_type") or line.description,
        "color": config.get("color") or config.get("color_ral"),
    }

def _mmg_spec(dossier: models.MMG) -> Optional[Dict]:
    if not dossier.width or not dossier.height:
        return None
    material = _material_from_value(dossier.material) or _material_from_text(dossier.material) or "ALU"
    return {
        "source": "mmg_dossier",
        "sale_order_line_id": None,
        "reference_suffix": dossier.reference.replace("/", "-"),
        "width": float(dossier.width),
        "height": float(dossier.height),
        "material": material,
        "quantity": 1,
        "system_type": dossier.opening_type or dossier.product_series or "Menuiserie",
        "color": dossier.color_ral,
    }

def _fabricable_specs_from_sale(sale: models.SaleOrder) -> List[Dict]:
    specs = []
    for dossier in sale.mmg_dossiers or []:
        spec = _mmg_spec(dossier)
        if spec:
            specs.append(spec)
    if specs:
        return specs
    for line in sale.lines:
        spec = _line_visual_spec(line)
        if spec:
            specs.append(spec)
    return specs

def _ensure_first_planning_step(db: Session, order: models.Order) -> None:
    existing_plan = db.query(models.Planning).filter(models.Planning.order_id == order.id).first()
    if existing_plan:
        return
    material = order.material.value if hasattr(order.material, "value") else order.material
    first_station = db.query(models.Station).filter(
        models.Station.material == material
    ).order_by(models.Station.order_index.asc()).first()
    db.add(
        models.Planning(
            order_id=order.id,
            station=first_station.code if first_station else f"{material}_DEBIT",
            priority=10,
        )
    )

def _link_active_reservations_to_order(db: Session, sale_id: int, order: models.Order) -> int:
    reservations = _active_workshop_reservations_for_sale(db, sale_id).filter(
        models.StockReservation.sale_order_id == sale_id,
        models.StockReservation.production_order_id.is_(None),
    ).all()
    for reservation in reservations:
        reservation.production_order_id = order.id
        reservation.order_reference = order.reference
    return len(reservations)

def _active_workshop_reservations_for_sale(db: Session, sale_id: int):
    return db.query(models.StockReservation).join(models.StockReservation.lines).filter(
        models.StockReservation.sale_order_id == sale_id,
        models.StockReservation.status == "reserved",
        models.StockReservationLine.status == "reserved",
        models.StockReservationLine.reserved_quantity > 0,
        or_(
            models.StockReservation.source_label.is_(None),
            ~models.StockReservation.source_label.in_(["devis libre", "devis_libre"]),
        ),
    ).distinct()

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

@router.get("/", response_model=List[schemas.SaleOrderSchema], dependencies=AUTH_DEPENDENCIES)
def list_sales(db: Session = Depends(get_db)):
    sales = (
        db.query(models.SaleOrder)
        .options(joinedload(models.SaleOrder.lines).joinedload(models.SaleOrderLine.variant).joinedload(models.ProductVariant.product))
        .order_by(models.SaleOrder.created_at.desc())
        .all()
    )
    for sale in sales:
        annotate_sale_availability(db, sale)
    return sales

class AIQuoteRequest(BaseModel):
    prompt: str

import urllib.request

@router.post("/ai-quote", dependencies=AUTH_DEPENDENCIES)
def generate_ai_quote(req: AIQuoteRequest, db: Session = Depends(get_db)):
    """
    Copilote Commercial (IA). Zero UI Approach.
    Gère la génération de devis ET la configuration dynamique du pipeline.
    """
    margin_rule = db.query(models.BusinessRule).filter(models.BusinessRule.rule_key == 'coef_marge_matiere').first()
    margin = float(margin_rule.value) if margin_rule else 1.8
    
    # Get current stages to pass to context
    config = db.query(models.AppConfig).filter(models.AppConfig.category == "PIPELINE_STAGES").first()
    import json
    current_stages = json.loads(config.value) if config else [
        { "id": 'DRAFT', "title": 'Brouillons' },
        { "id": 'SENT', "title": 'Envoyés (Négo)' },
        { "id": 'VALIDATED', "title": 'Gagnés (Signés)' },
        { "id": 'IN_DESIGN', "title": "Bureau d'Études" },
        { "id": 'READY_FOR_PROD', "title": 'Prêts pour Prod' },
        { "id": 'IN_PRODUCTION', "title": 'En Production' }
    ]
    stages_json = json.dumps(current_stages, ensure_ascii=False)

    system_prompt = f"""Tu es un Copilote Commercial IA (Approche Zero UI).
L'utilisateur va formuler une demande en langage naturel.
Tu dois analyser l'intention et renvoyer UNIQUEMENT DU JSON valide.

Il y a DEUX actions possibles :
1. "create_quote" : L'utilisateur veut générer un devis.
2. "update_stages" : L'utilisateur veut configurer/modifier/ajouter/supprimer les étapes du pipeline Kanban.

Si l'action est "update_stages", voici les étapes actuelles : {stages_json}.
Applique la modification demandée et renvoie TOUTES les étapes dans le tableau "stages".

Le JSON de sortie DOIT avoir ce format exact selon l'action :
Pour créer un devis :
{{
  "action": "create_quote",
  "client_name": "Nom du client",
  "lines": [
    {{ "description": "Baie Coulissante", "quantity": 1, "unit_price": 450000, "discount_pct": 0 }}
  ]
}}

Pour modifier le pipeline :
{{
  "action": "update_stages",
  "stages": [
    {{ "id": "DRAFT", "title": "Brouillons" }},
    ... (toutes les étapes mises à jour)
  ]
}}

Prix d'achat de base approximatifs : Baie (500€), Fenetre (150€), Porte (300€).
Tu DOIS multiplier ces prix de base par le coefficient de {margin} pour le unit_price.
"""
    
    ai_response_json = None
    
    # 1. Tentative OpenAI
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        try:
            url = "https://api.openai.com/v1/chat/completions"
            data = json.dumps({
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": req.prompt}
                ],
                "response_format": {"type": "json_object"}
            }).encode("utf-8")
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {openai_key}"
            }
            request = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(request, timeout=10) as response:
                result = json.loads(response.read().decode())
                content = result["choices"][0]["message"]["content"]
                ai_response_json = json.loads(content)
        except Exception as e:
            print(f"Erreur OpenAI: {e}")
            
    # 2. Tentative Ollama
    if not ai_response_json:
        try:
            url = "http://localhost:11434/api/generate"
            data = json.dumps({
                "model": "mistral",
                "prompt": f"{system_prompt}\nRequête utilisateur: {req.prompt}\nRéponds uniquement en JSON:",
                "stream": False,
                "format": "json"
            }).encode("utf-8")
            
            request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(request, timeout=15) as response:
                result = json.loads(response.read().decode())
                ai_response_json = json.loads(result["response"])
        except Exception as e:
            print(f"Erreur Ollama: {e}")

    # 3. Fallback
    if not ai_response_json:
        prompt_lower = req.prompt.lower()
        if "étape" in prompt_lower or "etape" in prompt_lower or "pipeline" in prompt_lower:
            ai_response_json = {
                "action": "update_stages",
                "stages": current_stages
            }
        else:
            client_name = "Client Inconnu"
            if "pour " in prompt_lower:
                parts = prompt_lower.split("pour ")
                if len(parts) > 1:
                    client_name = parts[1].split()[0].capitalize()
            ai_response_json = {
                "action": "create_quote",
                "client_name": client_name,
                "lines": [{"description": "Menuiserie Sur Mesure", "quantity": 1, "unit_price": 100000.0, "discount_pct": 0}]
            }

    # Execute Action
    action = ai_response_json.get("action", "create_quote")
    
    if action == "update_stages":
        new_stages = ai_response_json.get("stages", [])
        if not config:
            config = models.AppConfig(category="PIPELINE_STAGES", value=json.dumps(new_stages))
            db.add(config)
        else:
            config.value = json.dumps(new_stages)
        db.commit()
        return {"type": "stages_updated", "message": "Les étapes du pipeline ont été mises à jour."}
    
    # Default: create_quote
    final_lines = []
    for l in ai_response_json.get("lines", []):
        final_lines.append({
            "variant_id": 1,
            "description": l.get("description", "Article généré"),
            "quantity": l.get("quantity", 1),
            "unit_price": l.get("unit_price", 100000),
            "discount_pct": l.get("discount_pct", 0)
        })

    return {
        "type": "quote_draft",
        "quote": {
            "client_name": ai_response_json.get("client_name", "Client Inconnu"),
            "client_contact": "",
            "client_email": "",
            "client_address": "",
            "validity_days": 15,
            "tax_rate": 20.0,
            "currency": "EUR",
            "workflow_type": "FABRICATION_ESTIMATE",
            "notes": f"Devis généré par IA Copilot basé sur : '{req.prompt}'",
            "lines": final_lines
        }
    }

@router.get("/stages", dependencies=AUTH_DEPENDENCIES)
def get_pipeline_stages(db: Session = Depends(get_db)):
    config = db.query(models.AppConfig).filter(models.AppConfig.category == "PIPELINE_STAGES").first()
    import json
    if config:
        return json.loads(config.value)
    return [
        { "id": 'DRAFT', "title": 'Brouillons' },
        { "id": 'SENT', "title": 'Envoyés (Négo)' },
        { "id": 'VALIDATED', "title": 'Gagnés (Signés)' },
        { "id": 'IN_DESIGN', "title": "Bureau d'Études" },
        { "id": 'READY_FOR_PROD', "title": 'Prêts pour Prod' },
        { "id": 'IN_PRODUCTION', "title": 'En Production' }
    ]


@router.post("/", response_model=schemas.SaleOrderSchema, dependencies=AUTH_DEPENDENCIES)
def create_sale_order(
    order_req: schemas.SaleOrderCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    date_str = datetime.now().strftime("%Y-%m-%d-%H%M")
    ref = f"DEV-{date_str}"
    workflow_type = _normalise_sale_workflow_type(order_req.workflow_type)
    
    order = models.SaleOrder(
        reference=ref,
        client_name=order_req.client_name,
        client_contact=order_req.client_contact,
        client_email=order_req.client_email,
        client_address=order_req.client_address,
        validity_days=order_req.validity_days,
        tax_rate=order_req.tax_rate,
        currency=order_req.currency,
        notes=order_req.notes,
        status="DRAFT",
        workflow_type=workflow_type,
        author=current_user.get("sub", "unknown")
    )
    db.add(order)
    db.flush()
    
    for l in order_req.lines:
        line_type, _variant = _resolve_sale_line(db, l)
        line = models.SaleOrderLine(
            order_id=order.id,
            line_type=line_type,
            variant_id=l.variant_id,
            description=l.description,
            quantity=l.quantity,
            unit_price=l.unit_price,
            discount_pct=l.discount_pct,
            visual_config=l.visual_config
        )
        db.add(line)
        
    db.commit()
    order = _load_sale(db, order.id)
    annotate_sale_availability(db, order)
    return order

@router.get("/{order_id}", response_model=schemas.SaleOrderSchema, dependencies=AUTH_DEPENDENCIES)
def get_sale_order(order_id: int, db: Session = Depends(get_db)):
    order = _load_sale(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Devis introuvable.")
    annotate_sale_availability(db, order)
    _attach_sale_traceability(db, order)
    return order

@router.post("/{order_id}/prepare-workshop/preview", dependencies=AUTH_DEPENDENCIES)
async def preview_sale_workshop_preparation(
    order_id: int,
    files: List[UploadFile] = File(...),
    source_location: str = Form("WH/Stock"),
    db: Session = Depends(get_db),
):
    sale = db.query(models.SaleOrder).filter(models.SaleOrder.id == order_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Devis introuvable.")
    _ensure_sale_can_prepare_workshop(sale, allowed_statuses={"IN_DESIGN", "VALIDATED"})
    records, issues, _source_names = await _parse_workshop_uploads(files)
    return build_preview_payload(
        db,
        records,
        issues,
        source_location,
        sale_order_id=sale.id,
    )

@router.post("/{order_id}/prepare-workshop/reserve", dependencies=AUTH_DEPENDENCIES)
async def reserve_sale_workshop_preparation(
    order_id: int,
    files: List[UploadFile] = File(...),
    source_location: str = Form("WH/Stock"),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") not in ["ADMIN", "MANAGER"]:
        raise HTTPException(status_code=403, detail="Seul un manager peut préparer un débit atelier depuis un devis.")
    sale = db.query(models.SaleOrder).filter(models.SaleOrder.id == order_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Devis introuvable.")
    _ensure_sale_can_prepare_workshop(sale, allowed_statuses={"IN_DESIGN", "VALIDATED"})

    records, issues, source_names = await _parse_workshop_uploads(files)
    blocking_errors = [issue for issue in issues if issue.severity == "error"]
    if blocking_errors:
        raise HTTPException(status_code=400, detail="Fichier de débit non exploitable.")
    try:
        reservation = create_reservation(
            db,
            records,
            source_label=", ".join(source_names),
            created_by=current_user.get("sub", "Admin"),
            source_location=source_location,
            sale_order_id=sale.id,
            notes=notes or f"Préparation atelier depuis devis {sale.reference}",
        )
        sale.status = "READY_FOR_PROD"
        db.commit()
        db.refresh(reservation)
        return {
            "message": f"Préparation atelier réservée pour {sale.reference}.",
            "reservation_id": reservation.id,
            "reservation_reference": reservation.reference,
            "status": sale.status,
            "reserved_lines": len([line for line in reservation.lines if line.status == "reserved"]),
        }
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

@router.put("/{order_id}/status", dependencies=AUTH_DEPENDENCIES)
def update_sale_status(order_id: int, status: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    from ..core.events import EventBus
    order = _load_sale(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Devis introuvable.")
        
    import uuid
    if status == "SENT" and not order.signature_token:
        order.signature_token = str(uuid.uuid4())
        
    order.status = status
    reservation = None
    cancelled_reservations = 0
    if status == "CANCELLED":
        cancelled_reservations = _cancel_commercial_reservations_for_sale(db, order)
    else:
        try:
            reservation = _create_commercial_reservation_if_validated(db, order)
        except ValueError as exc:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    
    # --- INTERNAL AUTOMATION TRIGGER ---
    if status == "ACCEPTED":
        EventBus.on_quote_accepted(order.id, order.client_name, _sale_total_amount(order), background_tasks)
    
    # Generate portal link
    portal_link = None
    if order.signature_token:
        frontend_base_url = os.environ.get("FRONTEND_BASE_URL", "http://localhost:5000").rstrip("/")
        portal_link = f"{frontend_base_url}/portal/sign/{order.signature_token}"
        
    return {
        "message": f"Statut mis à jour : {status}",
        "portal_link": portal_link,
        "commercial_reservation_id": reservation.id if reservation else None,
        "cancelled_commercial_reservations": cancelled_reservations,
    }

@router.get("/portal/{token}")
def get_quote_by_token(token: str, db: Session = Depends(get_db)):
    # This endpoint is PUBLIC (no auth required) so the client can view it
    order = db.query(models.SaleOrder).filter(models.SaleOrder.signature_token == token).first()
    if not order:
        raise HTTPException(status_code=404, detail="Lien invalide ou expiré.")
        
    # Manually serialize to avoid returning sensitive internal IDs if needed, 
    # but for now we'll just return the order structure as expected by the frontend.
    return {
        "id": order.id,
        "reference": order.reference,
        "client_name": order.client_name,
        "client_contact": order.client_contact,
        "client_email": order.client_email,
        "client_address": order.client_address,
        "status": order.status,
        "validity_days": order.validity_days,
        "tax_rate": order.tax_rate,
        "currency": order.currency,
        "notes": order.notes,
        "created_at": order.created_at,
        "signed_at": order.signed_at,
        "lines": [
            {
                "description": l.description,
                "line_type": l.line_type,
                "variant_id": l.variant_id,
                "quantity": l.quantity,
                "unit_price": l.unit_price,
                "discount_pct": l.discount_pct,
                "visual_config": l.visual_config
            } for l in order.lines
        ]
    }

from fastapi import Request
@router.post("/portal/{token}/sign")
def sign_quote(token: str, request: Request, db: Session = Depends(get_db)):
    order = (
        db.query(models.SaleOrder)
        .options(
            joinedload(models.SaleOrder.lines)
            .joinedload(models.SaleOrderLine.variant)
            .joinedload(models.ProductVariant.product)
        )
        .filter(models.SaleOrder.signature_token == token)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Lien invalide ou expiré.")
        
    if order.status == "VALIDATED":
        return {"message": "Ce devis est déjà signé."}

    _ensure_sale_is_commercially_signable(order)
        
    client_ip = request.client.host
    # Capture timestamp
    current_time = datetime.utcnow()
    
    order.status = "VALIDATED"
    order.signed_at = current_time
    order.signed_by_ip = client_ip
    
    order.notes = (order.notes or "") + f"\n[SIGNATURE ÉLECTRONIQUE] Validé par le client le {current_time.strftime('%Y-%m-%d %H:%M:%S')} depuis l'IP: {client_ip}."

    try:
        reservation = _create_commercial_reservation_if_validated(db, order, actor="Portail client")
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    
    # --- AUTO-GENERATE NF525 INVOICE ---
    # Calculate Totals from Sale Order Lines
    subtotal = sum((l.unit_price or 0) * (l.quantity or 0) * (1 - (l.discount_pct or 0) / 100) for l in order.lines)
    tax_rate = order.tax_rate if hasattr(order, 'tax_rate') and order.tax_rate else 20.0
    tax_amount = subtotal * (tax_rate / 100.0)
    total = subtotal + tax_amount
    
    new_invoice = models.Invoice(
        reference=generate_invoice_reference(db),
        sale_order_id=order.id,
        client_name=order.client_name,
        client_address=order.client_address or order.client_email,
        client_siret="", # Not in sale order currently
        due_date=current_time + timedelta(days=30), # Default 30 days
        status="UNPAID",
        subtotal=subtotal,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        total=total
    )
    db.add(new_invoice)
    db.flush()
    
    for line in order.lines:
        db_inv_line = models.InvoiceLine(
            invoice_id=new_invoice.id,
            description=line.description,
            quantity=line.quantity,
            unit_price=line.unit_price,
            tax_rate=tax_rate
        )
        db.add(db_inv_line)
        
    new_invoice.qr_code_hash = compute_qr_seal(new_invoice)
    
    db.commit()
    return {
        "message": "Devis signé avec succès et Facture d'acompte/définitive générée !",
        "commercial_reservation_id": reservation.id if reservation else None,
    }


@router.post("/{order_id}/deliver-free-sale", dependencies=AUTH_DEPENDENCIES)
def deliver_free_sale_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") not in ["ADMIN", "MANAGER"]:
        raise HTTPException(status_code=403, detail="Seul un manager peut valider une sortie client.")

    sale = (
        db.query(models.SaleOrder)
        .options(joinedload(models.SaleOrder.lines))
        .filter(models.SaleOrder.id == order_id)
        .first()
    )
    if not sale:
        raise HTTPException(status_code=404, detail="Devis introuvable.")
    if sale.workflow_type != "FREE_SALE":
        raise HTTPException(status_code=400, detail="La sortie client directe est réservée aux devis libres.")
    if sale.status not in ["VALIDATED", "ACCEPTED"]:
        raise HTTPException(status_code=400, detail="La sortie client nécessite un devis libre signé/validé.")

    reservation = (
        db.query(models.StockReservation)
        .options(joinedload(models.StockReservation.lines).joinedload(models.StockReservationLine.variant))
        .filter(
            models.StockReservation.sale_order_id == sale.id,
            models.StockReservation.status == "reserved",
            models.StockReservation.source_label.in_(["devis libre", "devis_libre"]),
        )
        .first()
    )
    if not reservation:
        raise HTTPException(status_code=400, detail="Aucune réservation commerciale active à livrer pour ce devis.")

    try:
        stats = consume_commercial_reservation(
            db,
            reservation,
            author=current_user.get("sub", "Admin"),
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    if stats.get("consumed_lines", 0) == 0:
        raise HTTPException(status_code=400, detail="Aucune ligne de stock réservée à sortir.")

    delivery_note = (
        db.query(models.DeliveryNote)
        .filter(models.DeliveryNote.sale_order_id == sale.id)
        .order_by(models.DeliveryNote.id.asc())
        .first()
    )
    if not delivery_note:
        delivery_note = models.DeliveryNote(
            reference=_generate_delivery_note_reference(db),
            order_id=None,
            sale_order_id=sale.id,
            client_name=sale.client_name,
            delivery_address=sale.client_address,
            contact_phone=sale.client_contact,
            status="DELIVERED",
            signed_at=datetime.utcnow(),
            delivery_notes=f"Sortie client depuis réservation {reservation.reference}.",
        )
        db.add(delivery_note)
        db.flush()
    else:
        delivery_note.status = "DELIVERED"
        delivery_note.signed_at = delivery_note.signed_at or datetime.utcnow()
        delivery_note.delivery_notes = delivery_note.delivery_notes or f"Sortie client depuis réservation {reservation.reference}."

    sale.status = "DELIVERED"
    sale.notes = (sale.notes or "") + f"\n[SORTIE CLIENT] Stock livré depuis la réservation {reservation.reference}."
    db.commit()
    return {
        "message": "Sortie client effectuée.",
        "reservation_id": reservation.id,
        "delivery_note_id": delivery_note.id,
        "delivery_note_reference": delivery_note.reference,
        **stats,
    }


@router.post("/{order_id}/launch-production", dependencies=AUTH_DEPENDENCIES)
def launch_production(order_id: int, db: Session = Depends(get_db)):
    sale = db.query(models.SaleOrder).filter(models.SaleOrder.id == order_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Devis introuvable.")
    _ensure_sale_can_prepare_workshop(sale)

    if sale.status not in ["READY_FOR_PROD", "IN_PRODUCTION"]:
        raise HTTPException(
            status_code=400,
            detail="Transmettre à l'atelier nécessite une préparation atelier avec stock réservé.",
        )

    existing_orders = (
        db.query(models.Order)
        .filter(models.Order.sale_order_id == sale.id)
        .order_by(models.Order.id.asc())
        .all()
    )
    if existing_orders:
        for order in existing_orders:
            _ensure_first_planning_step(db, order)
        linked_reservations = _link_active_reservations_to_order(db, sale.id, existing_orders[0])
        sale.status = "IN_PRODUCTION"
        db.commit()
        return {
            "message": "Dossier déjà transmis à l'atelier.",
            "created_orders": 0,
            "existing_orders": len(existing_orders),
            "linked_reservations": linked_reservations,
        }

    active_workshop_reservations = _active_workshop_reservations_for_sale(db, sale.id).count()
    if active_workshop_reservations == 0:
        raise HTTPException(
            status_code=400,
            detail="Transmettre à l'atelier nécessite une réservation atelier active. Préparez l'atelier et réservez le stock avant lancement.",
        )

    specs = _fabricable_specs_from_sale(sale)
    if not specs:
        raise HTTPException(
            status_code=400,
            detail="Aucune ligne fabricable avec dimensions réelles. Créez ou rattachez un métré avant transmission atelier.",
        )

    created_orders = []
    sale_ref = sale.reference.replace("DEV-", "").replace("/", "-")
    for index, spec in enumerate(specs, start=1):
        prod_ref = f"PROD-{sale_ref}-{spec['reference_suffix'] or index}"
        existing = db.query(models.Order).filter(models.Order.reference == prod_ref).first()
        if existing:
            created_orders.append(existing)
            continue
        prod_order = models.Order(
            reference=prod_ref,
            sale_order_id=sale.id,
            sale_order_line_id=spec.get("sale_order_line_id"),
            width=spec["width"],
            height=spec["height"],
            material=spec["material"],
            client_name=sale.client_name,
            color=spec.get("color"),
            quantity=spec["quantity"],
            system_type=spec.get("system_type"),
        )
        db.add(prod_order)
        db.flush()
        _ensure_first_planning_step(db, prod_order)
        created_orders.append(prod_order)

    linked_reservations = 0
    if created_orders:
        linked_reservations = _link_active_reservations_to_order(db, sale.id, created_orders[0])

    sale.status = "IN_PRODUCTION"
    db.commit()
    return {
        "message": "Dossier lancé en production avec succès.",
        "created_orders": len(created_orders),
        "existing_orders": 0,
        "linked_reservations": linked_reservations,
    }

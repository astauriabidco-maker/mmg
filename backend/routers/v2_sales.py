from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List

from ..database import get_db
from .. import models, schemas
from ..core.security import get_current_user

import io
from .v2_accounting import generate_invoice_reference, compute_qr_seal

router = APIRouter(
    prefix="/v2/sales",
    tags=["sales_v2"],
    responses={404: {"description": "Non trouvé"}}
)

AUTH_DEPENDENCIES = [Depends(get_current_user)]

@router.get("/", response_model=List[schemas.SaleOrderSchema], dependencies=AUTH_DEPENDENCIES)
def list_sales(db: Session = Depends(get_db)):
    return db.query(models.SaleOrder).order_by(models.SaleOrder.created_at.desc()).all()

class AIQuoteRequest(BaseModel):
    prompt: str

import urllib.request
import json
import os

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
def create_sale_order(order_req: schemas.SaleOrderCreate, db: Session = Depends(get_db)):
    date_str = datetime.now().strftime("%Y-%m-%d-%H%M")
    ref = f"DEV-{date_str}"
    
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
        author="Admin" # TODO link with user
    )
    db.add(order)
    db.flush()
    
    for l in order_req.lines:
        line = models.SaleOrderLine(
            order_id=order.id,
            variant_id=l.variant_id,
            description=l.description,
            quantity=l.quantity,
            unit_price=l.unit_price,
            discount_pct=l.discount_pct,
            visual_config=l.visual_config
        )
        db.add(line)
        
    db.commit()
    db.refresh(order)
    return order

@router.get("/{order_id}", response_model=schemas.SaleOrderSchema, dependencies=AUTH_DEPENDENCIES)
def get_sale_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(models.SaleOrder).filter(models.SaleOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Devis introuvable.")
    return order

@router.put("/{order_id}/status", dependencies=AUTH_DEPENDENCIES)
def update_sale_status(order_id: int, status: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    from ..core.events import EventBus
    order = db.query(models.SaleOrder).filter(models.SaleOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Devis introuvable.")
        
    import uuid
    if status == "SENT" and not order.signature_token:
        order.signature_token = str(uuid.uuid4())
        
    order.status = status
    db.commit()
    
    # --- INTERNAL AUTOMATION TRIGGER ---
    if status == "ACCEPTED":
        EventBus.on_quote_accepted(order.id, order.client_name, float(order.total_amount), background_tasks)
    
    # Generate portal link
    portal_link = None
    if order.signature_token:
        portal_link = f"http://localhost:5173/portal/sign/{order.signature_token}"
        
    return {"message": f"Statut mis à jour : {status}", "portal_link": portal_link}

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
        "created_at": order.created_at,
        "signed_at": order.signed_at,
        "lines": [
            {
                "description": l.description,
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
    order = db.query(models.SaleOrder).filter(models.SaleOrder.signature_token == token).first()
    if not order:
        raise HTTPException(status_code=404, detail="Lien invalide ou expiré.")
        
    if order.status == "VALIDATED":
        return {"message": "Ce devis est déjà signé."}
        
    client_ip = request.client.host
    # Capture timestamp
    current_time = datetime.utcnow()
    
    order.status = "VALIDATED"
    order.signed_at = current_time
    order.signed_by_ip = client_ip
    
    order.notes = (order.notes or "") + f"\n[SIGNATURE ÉLECTRONIQUE] Validé par le client le {current_time.strftime('%Y-%m-%d %H:%M:%S')} depuis l'IP: {client_ip}."
    
    # --- AUTO-GENERATE NF525 INVOICE ---
    # Calculate Totals from Sale Order Lines
    subtotal = sum(l.unit_price * l.quantity for l in order.lines)
    tax_rate = order.tax_rate if hasattr(order, 'tax_rate') and order.tax_rate else 20.0
    tax_amount = subtotal * (tax_rate / 100.0)
    total = subtotal + tax_amount
    
    new_invoice = models.Invoice(
        reference=generate_invoice_reference(db),
        sale_order_id=order.id,
        client_name=order.client_name,
        client_address=order.client_email, # using email as fallback if address not present
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
    return {"message": "Devis signé avec succès et Facture d'acompte/définitive générée !"}

@router.post("/{order_id}/launch-production", dependencies=AUTH_DEPENDENCIES)
def launch_production(order_id: int, db: Session = Depends(get_db)):
    sale = db.query(models.SaleOrder).filter(models.SaleOrder.id == order_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Devis introuvable.")
        
    if sale.status != "READY_FOR_PROD":
        raise HTTPException(status_code=400, detail="Seul un dossier dont le BOM a été importé (READY_FOR_PROD) peut être lancé en production.")
        
    # Create production orders based on sale lines
    for i, line in enumerate(sale.lines):
        # We need to extract material from description or assume ALU if not specified
        material = "ALU"
        if "PVC" in line.description.upper():
            material = "PVC"
            
        prod_ref = f"PROD-{sale.reference.replace('DEV-', '')}-{i+1}"
        
        prod_order = models.Order(
            reference=prod_ref,
            width=1000, # Mock sizes, in reality we should link SaleOrderLine to MMG specs
            height=1000,
            material=material,
            client_name=sale.client_name,
            quantity=int(line.quantity),
            system_type="Ouvrant à la Française"
        )
        db.add(prod_order)
        db.flush()
        
        # Dynamic First Station Logic
        # We only create the very first planning step (lowest order_index for this material).
        # When this step is DONE, v2_planning.py will automatically create the next step in the sequence.
        first_station = db.query(models.Station).filter(
            models.Station.material == material
        ).order_by(models.Station.order_index.asc()).first()
        
        if first_station:
            plan = models.Planning(
                order_id=prod_order.id,
                station=first_station.code,
                priority=10
            )
            db.add(plan)
        else:
            # Fallback if no stations configured
            plan = models.Planning(
                order_id=prod_order.id,
                station=f"{material}_DEBIT",
                priority=10
            )
            db.add(plan)
            
    sale.status = "IN_PRODUCTION"
    db.commit()
    return {"message": "Dossier lancé en production avec succès !"}

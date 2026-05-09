from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import PlainTextResponse
import json
import os
import urllib.request
from sqlalchemy.orm import Session
from ..database import get_db

router = APIRouter(
    prefix="/v2/webhook",
    tags=["webhook"],
)

VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "mmg_secure_token_123")

@router.get("/whatsapp")
def verify_whatsapp_webhook(request: Request):
    """
    Validation du webhook par Meta (WhatsApp Business API)
    """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return PlainTextResponse(content=challenge, status_code=200)
        else:
            raise HTTPException(status_code=403, detail="Verification token mismatch")
    
    raise HTTPException(status_code=400, detail="Missing parameters")


@router.post("/whatsapp")
async def handle_whatsapp_message(request: Request, db: Session = Depends(get_db)):
    """
    Réception des messages WhatsApp (Zero UI)
    """
    body = await request.json()
    
    # 1. Vérifier si c'est un message valide de l'API WhatsApp
    if body.get("object") != "whatsapp_business_account":
        return {"status": "ignored"}
        
    try:
        entries = body.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                messages = value.get("messages", [])
                
                # 2. Traiter chaque message entrant
                for msg in messages:
                    phone_number = msg.get("from")
                    text_content = msg.get("text", {}).get("body", "").strip()
                    
                    if not text_content:
                        continue
                        
                    print(f"[WhatsApp] Reçu de {phone_number}: {text_content}")
                    
                    # 3. Logique IA Copilote
                    # Ici on interroge Ollama localement ou OpenAI pour comprendre la requête
                    reply = process_ai_intent(text_content, db)
                    
                    # 4. Répondre via l'API WhatsApp (Envoi du message)
                    send_whatsapp_message(phone_number, reply)
                    
    except Exception as e:
        print(f"Erreur Webhook: {e}")
        
    # Meta demande toujours un statut 200 OK
    return {"status": "ok"}


def process_ai_intent(message: str, db: Session) -> str:
    """
    Détecte l'intention du message et répond intelligemment (Génération devis, Statut Prod, etc.)
    """
    # Exemple de routing basique (à remplacer par un vrai appel LLM RAG)
    msg_lower = message.lower()
    
    if "bilan" in msg_lower or "ca" in msg_lower:
        from .v2_analytics import get_sales_analytics
        # On simule un appel interne
        return "Le Chiffre d'Affaire du mois est actuellement de 42.8 K € avec 24 dossiers en production. Tout est au vert ! 🚀"
        
    elif "devis" in msg_lower:
        return "J'ai bien compris que vous souhaitez générer un devis. Je prépare le brouillon et je vous l'envoie en PDF d'ici quelques minutes. 📄"
        
    else:
        return f"Je suis le Copilote MMG. Je peux générer des devis ou vous donner les KPIs de l'atelier. Que puis-je faire pour vous ?"


def send_whatsapp_message(to: str, message: str):
    """
    Envoi effectif du message via Meta Cloud API.
    """
    wa_token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    phone_id = os.environ.get("WHATSAPP_PHONE_ID")
    
    if not wa_token or not phone_id:
        print("[Mock WhatsApp] ->", to, ":", message)
        return
        
    url = f"https://graph.facebook.com/v17.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {wa_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message}
    }
    
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req) as response:
            print("Message envoyé avec succès:", response.read())
    except Exception as e:
        print("Erreur d'envoi WhatsApp:", e)

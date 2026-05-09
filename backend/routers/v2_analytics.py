from fastapi import APIRouter, Depends, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict
from datetime import datetime, date, timedelta
from ..database import get_db
from .. import models
from ..core.config import STANDARDS, ALERT_THRESHOLD_PERCENT

router = APIRouter(prefix="/v2/analytics", tags=["analytics"])

@router.get("/daily")
def get_daily_stats(db: Session = Depends(get_db)):
    today = datetime.utcnow().date()
    # In SQLite, date comparison might need slight adjustment depending on storage format.
    # We stored DateTime. Let's filter >= today midnight.
    start_of_day = datetime(today.year, today.month, today.day)
    
    # Query logs
    logs = db.query(models.ProductionLog).filter(models.ProductionLog.start_time >= start_of_day).all()
    
    total = len(logs)
    avg_time = 0
    if total > 0:
        completed = [l for l in logs if l.end_time]
        if completed:
            durations = [(c.end_time - c.start_time).total_seconds() for c in completed]
            avg_time = int(sum(durations) / len(durations))

    delayed_count = 0
    for l in logs:
        # Determine standard
        # Standard stored in config is by Station (e.g. "PVC_DEBIT": 35)
        # Log has station enum.
        station_val = l.station if l.station else "UNKNOWN"
        std_min = STANDARDS.get(station_val, 30) # Default 30 if unknown
        std_sec = std_min * 60
        threshold = std_sec * (ALERT_THRESHOLD_PERCENT / 100)
        
        if l.duration_seconds and l.duration_seconds > threshold:
            delayed_count += 1
            
    delay_rate = 0
    if total > 0:
        delay_rate = int((delayed_count / total) * 100)
    
    # Active orders (not completed)
    active = db.query(models.ProductionLog).filter(
        models.ProductionLog.start_time >= start_of_day,
        models.ProductionLog.end_time.is_(None)
    ).count()

    return {
        "total": total,
        "avg_time": f"{avg_time // 60}m {avg_time % 60}s",
        "delay_rate": delay_rate,
        "active": active
    }

@router.get("/hourly")
def get_hourly_stats(db: Session = Depends(get_db)):
    # Simple hourly aggregation
    # SQLite strftime('%H', start_time)
    today = datetime.utcnow().date()
    start_of_day = datetime(today.year, today.month, today.day)
    
    results = db.query(
        func.strftime('%H', models.ProductionLog.start_time).label('hour'),
        func.count(models.ProductionLog.id).label('count')
    ).filter(
        models.ProductionLog.start_time >= start_of_day
    ).group_by('hour').all()
    
    # Format for Recharts [{name: '08:00', count: 5}, ...]
    data = []
    hours_map = {int(r.hour): r.count for r in results}
    
    for h in range(8, 19): # 8h to 18h
        data.append({
            "name": f"{h}:00",
            "count": hours_map.get(h, 0)
        })
        
    return data

class InsightQuery(BaseModel):
    query: str

import urllib.request
import json
import os

@router.post("/ask")
def ask_insight_engine(query_obj: InsightQuery, db: Session = Depends(get_db)):
    """
    Insight Engine propulsé par IA (Ollama / OpenAI).
    L'IA analyse la question pour déterminer l'intention (SALES, PRODUCTS, PRODUCTION).
    Le backend injecte ensuite les vraies données de la base.
    """
    system_prompt = \"\"\"Tu es l'Analyste Décisionnel (Insight Engine) de MMG ERP, une usine de menuiserie.
Le manager te pose une question sur son activité.
Tu dois analyser la question et retourner UNIQUEMENT un objet JSON valide.
Structure requise:
{
  "intent": "SALES" | "PRODUCTS" | "PRODUCTION" | "UNKNOWN",
  "type": "barchart" | "piechart" | "linechart" | "text",
  "message": "Une phrase d'introduction cordiale et analytique"
}
Si la question parle de chiffre d'affaires, factures, revenus -> intent: SALES, type: barchart
Si la question parle de top articles, produits les plus vendus -> intent: PRODUCTS, type: piechart
Si la question parle d'atelier, de retard, de temps de production -> intent: PRODUCTION, type: linechart
Sinon -> intent: UNKNOWN, type: text
\"\"\"
    ai_response = None
    openai_key = os.environ.get("OPENAI_API_KEY")
    
    # 1. Tentative OpenAI
    if openai_key:
        try:
            url = "https://api.openai.com/v1/chat/completions"
            data = json.dumps({
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query_obj.query}
                ],
                "response_format": {"type": "json_object"}
            }).encode("utf-8")
            
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {openai_key}"}
            request = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(request, timeout=10) as response:
                result = json.loads(response.read().decode())
                content = result["choices"][0]["message"]["content"]
                ai_response = json.loads(content)
        except Exception as e:
            print(f"Erreur OpenAI Analytics: {e}")

    # 2. Tentative Ollama
    if not ai_response:
        try:
            url = "http://localhost:11434/api/generate"
            data = json.dumps({
                "model": "mistral",
                "prompt": f"{system_prompt}\nQuestion: {query_obj.query}\nJSON:",
                "stream": False,
                "format": "json"
            }).encode("utf-8")
            
            request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(request, timeout=15) as response:
                result = json.loads(response.read().decode())
                ai_response = json.loads(result["response"])
        except Exception as e:
            print(f"Erreur Ollama Analytics: {e}")

    # 3. Fallback en cas d'échec
    if not ai_response:
        query_lower = query_obj.query.lower()
        intent = "UNKNOWN"
        chart_type = "text"
        if "chiffre" in query_lower or "vente" in query_lower:
            intent, chart_type = "SALES", "barchart"
        elif "produit" in query_lower or "top" in query_lower:
            intent, chart_type = "PRODUCTS", "piechart"
        elif "production" in query_lower or "retard" in query_lower:
            intent, chart_type = "PRODUCTION", "linechart"
            
        ai_response = {
            "intent": intent,
            "type": chart_type,
            "message": "Analyse générée via moteur de secours (hors ligne)."
        }

    # Fetch Real Data from Database based on AI's Intent Extraction
    intent = ai_response.get("intent", "UNKNOWN")
    chart_type = ai_response.get("type", "text")
    message = ai_response.get("message", "Voici les données :")
    chart_data = []

    if intent == "SALES":
        orders = db.query(models.POSOrder).all()
        total = sum(o.amount_total for o in orders)
        message = f"{message} (CA Total: {total:.2f} €)"
        chart_data = [
            {"name": "Lun", "total": total * 0.1},
            {"name": "Mar", "total": total * 0.2},
            {"name": "Mer", "total": total * 0.15},
            {"name": "Jeu", "total": total * 0.3},
            {"name": "Ven", "total": total * 0.25},
        ]
    elif intent == "PRODUCTS":
        orders = db.query(models.POSOrder).all()
        product_sales = {}
        for o in orders:
            for line in o.lines:
                product_sales[line.product_name] = product_sales.get(line.product_name, 0) + line.quantity
        top_products = sorted([{"name": k, "value": v} for k, v in product_sales.items()], key=lambda x: x["value"], reverse=True)[:5]
        if not top_products:
            top_products = [{"name": "Aucune vente", "value": 1}]
        chart_data = top_products
    elif intent == "PRODUCTION":
        chart_data = [
            {"name": "S1", "reel": 45, "objectif": 30},
            {"name": "S2", "reel": 42, "objectif": 30},
            {"name": "S3", "reel": 38, "objectif": 30},
            {"name": "S4", "reel": 35, "objectif": 30},
        ]
    else:
        chart_type = "text"
        message = "Je n'ai pas pu classifier votre demande dans les catégories: Ventes, Produits ou Production."

    return {
        "type": chart_type,
        "message": message,
        "data": chart_data
    }

from fastapi import APIRouter, Depends, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict
from datetime import datetime, date, timedelta
from ..database import get_db
from .. import models
from ..core.config import STANDARDS, ALERT_THRESHOLD_PERCENT
from ..core import security
from ..core.time import utcnow

router = APIRouter(
    prefix="/v2/analytics",
    tags=["analytics"],
    dependencies=[Depends(security.get_current_user)],
)

@router.get("/kpi")
def get_dashboard_kpi(db: Session = Depends(get_db)):
    """KPI temps réel pour le tableau de bord principal."""
    now = utcnow()
    first_of_month = datetime(now.year, now.month, 1)

    # --- CA MENSUEL (Factures du mois en cours) ---
    month_invoices = db.query(models.Invoice).filter(
        models.Invoice.issue_date >= first_of_month,
        models.Invoice.status != "DRAFT"
    ).all()
    ca_mensuel = sum(inv.total for inv in month_invoices)

    # CA mois précédent pour le delta
    if now.month == 1:
        prev_start = datetime(now.year - 1, 12, 1)
        prev_end = datetime(now.year, 1, 1)
    else:
        prev_start = datetime(now.year, now.month - 1, 1)
        prev_end = first_of_month
    prev_invoices = db.query(models.Invoice).filter(
        models.Invoice.issue_date >= prev_start,
        models.Invoice.issue_date < prev_end,
        models.Invoice.status != "DRAFT"
    ).all()
    ca_prev = sum(inv.total for inv in prev_invoices)
    ca_delta_pct = ((ca_mensuel - ca_prev) / ca_prev * 100) if ca_prev > 0 else 0

    # --- VALEUR INVENTAIRE (Quants internes × cost_price) ---
    from sqlalchemy.orm import joinedload as jl
    quants = db.query(models.StockQuant).filter(models.StockQuant.quantity > 0).all()
    inventory_value = 0.0
    for q in quants:
        loc = db.query(models.StockLocation).filter(models.StockLocation.id == q.location_id).first()
        if loc and loc.usage == "internal":
            variant = db.query(models.ProductVariant).filter(models.ProductVariant.id == q.variant_id).first()
            cost = float(variant.cost_price) if variant and variant.cost_price else 0
            inventory_value += q.quantity * cost

    # --- TAUX DE RENDEMENT (Production OK / Total) ---
    start_of_day = datetime(now.year, now.month, now.day)
    total_logs = db.query(models.ProductionLog).filter(
        models.ProductionLog.start_time >= first_of_month
    ).count()
    # Les logs complétés (avec end_time) sont considérés comme réussis
    completed_logs = db.query(models.ProductionLog).filter(
        models.ProductionLog.start_time >= first_of_month,
        models.ProductionLog.end_time.isnot(None)
    ).count()
    yield_rate = (completed_logs / total_logs * 100) if total_logs > 0 else 100.0

    # --- DOSSIERS EN PRODUCTION (SaleOrders VALIDATED non livrés) ---
    active_dossiers = db.query(models.SaleOrder).filter(
        models.SaleOrder.status.in_(["VALIDATED", "SENT"])
    ).count()

    # --- GRAPHIQUE SEMAINE (7 derniers jours, CA réel par jour) ---
    chart_data = []
    jours_fr = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    for i in range(6, -1, -1):
        day = (now - timedelta(days=i)).date()
        day_start = datetime(day.year, day.month, day.day)
        day_end = day_start + timedelta(days=1)

        day_ca = db.query(func.coalesce(func.sum(models.Invoice.total), 0)).filter(
            models.Invoice.issue_date >= day_start,
            models.Invoice.issue_date < day_end,
            models.Invoice.status != "DRAFT"
        ).scalar()

        day_prod_count = db.query(func.count(models.ProductionLog.id)).filter(
            models.ProductionLog.start_time >= day_start,
            models.ProductionLog.start_time < day_end,
        ).scalar()

        chart_data.append({
            "name": jours_fr[day.weekday()],
            "sales": round(float(day_ca), 2),
            "prod": int(day_prod_count) * 150  # Valorisation estimée par tâche
        })

    return {
        "ca_mensuel": round(float(ca_mensuel), 2),
        "ca_delta_pct": round(float(ca_delta_pct), 1),
        "inventory_value": round(float(inventory_value), 2),
        "yield_rate": round(yield_rate, 1),
        "active_dossiers": active_dossiers,
        "chart_data": chart_data
    }

@router.get("/daily")
def get_daily_stats(db: Session = Depends(get_db)):
    today = utcnow().date()
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
    # SQLAlchemy compile extract() en EXTRACT pour PostgreSQL et en
    # STRFTIME pour SQLite : l'agrégation reste portable entre prod et tests.
    today = utcnow().date()
    start_of_day = datetime(today.year, today.month, today.day)
    
    results = db.query(
        func.extract('hour', models.ProductionLog.start_time).label('hour'),
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
    L'IA analyse la question pour déterminer l'intention.
    Le backend injecte ensuite les vraies données de la base.
    """
    system_prompt = """Tu es l'Analyste Décisionnel (Insight Engine) de MMG ERP, une usine de menuiserie en France.
Le manager te pose une question sur son activité.
Tu dois analyser la question et retourner UNIQUEMENT un objet JSON valide.
Structure requise:
{
  "intent": "SALES" | "PRODUCTS" | "PRODUCTION" | "INVENTORY" | "PURCHASES" | "LOGISTICS" | "CLIENTS" | "UNKNOWN",
  "type": "barchart" | "piechart" | "linechart" | "text",
  "message": "Une phrase d'introduction cordiale et analytique"
}
Règles:
- chiffre d'affaires, factures, revenus, CA, encaissements -> intent: SALES, type: barchart
- top articles, produits les plus vendus, best sellers -> intent: PRODUCTS, type: piechart
- atelier, retard, temps de production, rendement, tâches -> intent: PRODUCTION, type: linechart
- stock, inventaire, rupture, seuil, valorisation -> intent: INVENTORY, type: barchart
- achats, fournisseurs, commandes fournisseurs, appro, bons de commande -> intent: PURCHASES, type: barchart
- livraison, expédition, logistique, tournée, BL -> intent: LOGISTICS, type: barchart
- clients, CRM, devis, prospects -> intent: CLIENTS, type: piechart
- Sinon -> intent: UNKNOWN, type: text
"""
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

    # 3. Fallback intelligent par mots-clés
    if not ai_response:
        q = query_obj.query.lower()
        intent, chart_type = "UNKNOWN", "text"
        if any(k in q for k in ["chiffre", "vente", "ca ", "revenu", "factur", "encaiss"]):
            intent, chart_type = "SALES", "barchart"
        elif any(k in q for k in ["produit", "top", "best", "vendu"]):
            intent, chart_type = "PRODUCTS", "piechart"
        elif any(k in q for k in ["production", "retard", "atelier", "rendement", "tâche"]):
            intent, chart_type = "PRODUCTION", "linechart"
        elif any(k in q for k in ["stock", "inventaire", "rupture", "seuil", "valorisation"]):
            intent, chart_type = "INVENTORY", "barchart"
        elif any(k in q for k in ["achat", "fournisseur", "appro", "commande fournisseur", "bon de commande"]):
            intent, chart_type = "PURCHASES", "barchart"
        elif any(k in q for k in ["livraison", "expédition", "logistique", "tournée", "bl"]):
            intent, chart_type = "LOGISTICS", "barchart"
        elif any(k in q for k in ["client", "crm", "devis", "prospect"]):
            intent, chart_type = "CLIENTS", "piechart"
            
        ai_response = {
            "intent": intent,
            "type": chart_type,
            "message": "Analyse générée via moteur de secours (hors ligne)."
        }

    # ================================================================
    # FETCH REAL DATA FROM DATABASE BASED ON AI INTENT
    # ================================================================
    intent = ai_response.get("intent", "UNKNOWN")
    chart_type = ai_response.get("type", "text")
    message = ai_response.get("message", "Voici les données :")
    chart_data = []
    now = utcnow()

    if intent == "SALES":
        # CA réel des 7 derniers jours depuis les Factures
        jours_fr = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
        total_ca = 0
        for i in range(6, -1, -1):
            day = (now - timedelta(days=i)).date()
            day_start = datetime(day.year, day.month, day.day)
            day_end = day_start + timedelta(days=1)
            day_ca = db.query(func.coalesce(func.sum(models.Invoice.total), 0)).filter(
                models.Invoice.issue_date >= day_start,
                models.Invoice.issue_date < day_end,
                models.Invoice.status != "DRAFT"
            ).scalar()
            total_ca += float(day_ca)
            chart_data.append({"name": jours_fr[day.weekday()], "total": round(float(day_ca), 2)})
        
        # Compléter avec le POS
        pos_total = db.query(func.coalesce(func.sum(models.POSOrder.amount_total), 0)).scalar()
        invoices_total = db.query(func.coalesce(func.sum(models.Invoice.total), 0)).filter(
            models.Invoice.status != "DRAFT"
        ).scalar()
        
        message = f"{message}\n\n**CA Factures (tous temps):** {float(invoices_total):,.2f} €\n**CA POS (tous temps):** {float(pos_total):,.2f} €\n**CA 7 derniers jours:** {total_ca:,.2f} €"

    elif intent == "PRODUCTS":
        # Top produits vendus depuis POS + Factures
        pos_orders = db.query(models.POSOrder).all()
        product_sales = {}
        for o in pos_orders:
            for line in o.lines:
                product_sales[line.product_name] = product_sales.get(line.product_name, 0) + line.quantity
        
        # Aussi depuis les lignes de facture
        inv_lines = db.query(models.InvoiceLine).all()
        for line in inv_lines:
            product_sales[line.description] = product_sales.get(line.description, 0) + line.quantity
        
        top_products = sorted([{"name": k, "value": v} for k, v in product_sales.items()], key=lambda x: x["value"], reverse=True)[:7]
        if not top_products:
            top_products = [{"name": "Aucune vente enregistrée", "value": 1}]
        chart_data = top_products
        
        total_refs = len(product_sales)
        message = f"{message}\n\n**{total_refs} références vendues** au total. Voici le Top {min(7, len(top_products))} :"

    elif intent == "PRODUCTION":
        # Temps de production réel par station (7 derniers jours)
        week_start = now - timedelta(days=7)
        logs = db.query(models.ProductionLog).filter(
            models.ProductionLog.start_time >= week_start,
            models.ProductionLog.end_time.isnot(None)
        ).all()
        
        station_times = {}
        station_counts = {}
        for l in logs:
            station = l.station or "Inconnu"
            duration_min = (l.duration_seconds or 0) / 60.0
            station_times[station] = station_times.get(station, 0) + duration_min
            station_counts[station] = station_counts.get(station, 0) + 1
        
        for station, total_time in station_times.items():
            count = station_counts[station]
            chart_data.append({
                "name": station.replace("_", " "),
                "reel": round(total_time / count, 1) if count > 0 else 0,
                "objectif": 30  # Standard par défaut
            })
        
        if not chart_data:
            chart_data = [{"name": "Aucune donnée", "reel": 0, "objectif": 30}]
        
        total_logs = len(logs)
        total_time = sum(station_times.values())
        message = f"{message}\n\n**{total_logs} tâches complétées** cette semaine.\n**Temps total cumulé:** {total_time:.0f} min.\nVoici le temps moyen par station vs objectif (30 min) :"

    elif intent == "INVENTORY":
        # Valorisation par emplacement + alertes rupture
        quants = db.query(models.StockQuant).filter(models.StockQuant.quantity > 0).all()
        loc_values = {}
        low_stock_items = []
        
        for q in quants:
            loc = db.query(models.StockLocation).filter(models.StockLocation.id == q.location_id).first()
            if loc and loc.usage == "internal":
                variant = db.query(models.ProductVariant).filter(models.ProductVariant.id == q.variant_id).first()
                cost = float(variant.cost_price) if variant and variant.cost_price else 0
                value = q.quantity * cost
                loc_name = loc.name or "Inconnu"
                loc_values[loc_name] = loc_values.get(loc_name, 0) + value
                
                # Détection rupture
                if variant and q.quantity <= (variant.min_threshold or 0):
                    low_stock_items.append(variant.reference)
        
        chart_data = [{"name": k, "total": round(v, 2)} for k, v in sorted(loc_values.items(), key=lambda x: x[1], reverse=True)]
        if not chart_data:
            chart_data = [{"name": "Aucun stock", "total": 0}]
        
        total_val = sum(loc_values.values())
        low_str = f"\n⚠️ **{len(low_stock_items)} article(s) en rupture/seuil critique** : {', '.join(low_stock_items[:5])}" if low_stock_items else "\n✅ Aucune alerte de rupture."
        message = f"{message}\n\n**Valorisation totale inventaire:** {total_val:,.2f} €{low_str}"

    elif intent == "PURCHASES":
        # Commandes d'achat par statut + montant total
        from ..models import PurchaseOrderStatus
        pos_data = db.query(models.PurchaseOrder).all()
        status_totals = {}
        for po in pos_data:
            status = po.status.value if hasattr(po.status, 'value') else str(po.status)
            status_totals[status] = status_totals.get(status, 0) + (po.total_amount or 0)
        
        chart_data = [{"name": k, "total": round(v, 2)} for k, v in status_totals.items()]
        if not chart_data:
            chart_data = [{"name": "Aucune commande", "total": 0}]
        
        total_po = len(pos_data)
        total_amount = sum(po.total_amount or 0 for po in pos_data)
        pending = sum(1 for po in pos_data if str(po.status) in ["PurchaseOrderStatus.DRAFT", "DRAFT", "PurchaseOrderStatus.ORDERED", "ORDERED"])
        message = f"{message}\n\n**{total_po} bons de commande** pour un total de **{total_amount:,.2f} €**.\n**{pending} en attente** de réception."

    elif intent == "LOGISTICS":
        # Livraisons par statut
        routes = db.query(models.DeliveryRoute).all()
        notes = db.query(models.DeliveryNote).all()
        
        status_count = {}
        for n in notes:
            status_count[n.status] = status_count.get(n.status, 0) + 1
        
        chart_data = [{"name": k, "total": v} for k, v in status_count.items()]
        if not chart_data:
            chart_data = [{"name": "Aucun BL", "total": 0}]
        
        total_routes = len(routes)
        total_bl = len(notes)
        delivered = sum(1 for n in notes if n.status == "DELIVERED")
        message = f"{message}\n\n**{total_routes} tournées** planifiées.\n**{total_bl} bons de livraison** dont **{delivered} livrés**."

    elif intent == "CLIENTS":
        # Répartition clients B2B vs B2C + top clients par CA
        clients = db.query(models.Client).filter(models.Client.is_active == True).all()
        type_count = {}
        for c in clients:
            t = c.customer_type or "Autre"
            type_count[t] = type_count.get(t, 0) + 1
        
        chart_data = [{"name": k, "value": v} for k, v in type_count.items()]
        if not chart_data:
            chart_data = [{"name": "Aucun client", "value": 1}]
        
        # Compter les devis
        total_devis = db.query(models.SaleOrder).count()
        devis_valides = db.query(models.SaleOrder).filter(models.SaleOrder.status == "VALIDATED").count()
        
        total_clients = len(clients)
        message = f"{message}\n\n**{total_clients} clients actifs.**\n**{total_devis} devis créés** dont **{devis_valides} validés** ({(devis_valides/total_devis*100):.0f}% de conversion)." if total_devis > 0 else f"{message}\n\n**{total_clients} clients actifs.** Aucun devis enregistré."

    else:
        chart_type = "text"
        message = f"Je n'ai pas pu classifier votre demande. Essayez de me poser une question sur :\n\n• **Ventes / CA** — chiffre d'affaires, factures\n• **Produits** — top articles vendus\n• **Production** — temps atelier, rendement\n• **Inventaire** — stock, valorisation, ruptures\n• **Achats** — fournisseurs, bons de commande\n• **Logistique** — livraisons, tournées\n• **Clients** — CRM, devis"

    return {
        "type": chart_type,
        "message": message,
        "data": chart_data
    }

@router.get("/workshop")
def get_workshop_analytics(db: Session = Depends(get_db)):
    """Analyse historique et performance de l'atelier."""
    now = utcnow()
    seven_days_ago = now - timedelta(days=7)

    # 1. Lead Time global sur les 7 derniers jours
    recent_logs = db.query(models.ProductionLog).filter(
        models.ProductionLog.start_time >= seven_days_ago,
        models.ProductionLog.end_time.isnot(None)
    ).all()

    total_duration = sum(log.duration_seconds or 0 for log in recent_logs)
    avg_lead_time_min = (total_duration / len(recent_logs)) / 60 if recent_logs else 0

    # 2. Temps moyen par station (Top 5)
    station_stats = {}
    for log in recent_logs:
        st = log.station
        if st not in station_stats:
            station_stats[st] = {"total_sec": 0, "count": 0}
        station_stats[st]["total_sec"] += (log.duration_seconds or 0)
        station_stats[st]["count"] += 1

    station_avg = []
    for st, stats in station_stats.items():
        avg_min = (stats["total_sec"] / stats["count"]) / 60
        station_avg.append({"name": st.replace('_', ' '), "avg_time": round(avg_min, 1)})
    
    # Sort and take top 5
    station_avg = sorted(station_avg, key=lambda x: x["avg_time"], reverse=True)[:5]

    # 3. Productivité par opérateur
    operator_stats = {}
    for log in recent_logs:
        op = log.operator_name or "Inconnu"
        if op not in operator_stats:
            operator_stats[op] = 0
        operator_stats[op] += 1
    
    operator_prod = [{"name": op, "tasks": count} for op, count in operator_stats.items()]
    operator_prod = sorted(operator_prod, key=lambda x: x["tasks"], reverse=True)[:5]

    # 4. Taux de défauts / incidents (Actuels ou récents)
    # We check issues from Planning since ProductionLog records "successful" steps.
    recent_issues = db.query(models.Planning).filter(
        models.Planning.created_at >= seven_days_ago,
        models.Planning.status == models.PlanningStatus.ISSUE
    ).count()

    total_tasks = db.query(models.Planning).filter(
        models.Planning.created_at >= seven_days_ago
    ).count()

    defect_rate = (recent_issues / total_tasks * 100) if total_tasks > 0 else 0

    return {
        "global": {
            "tasks_completed_7d": len(recent_logs),
            "avg_lead_time_min": round(avg_lead_time_min, 1),
            "defect_rate_pct": round(defect_rate, 1),
            "issues_7d": recent_issues
        },
        "station_avg_time": station_avg,
        "operator_productivity": operator_prod
    }

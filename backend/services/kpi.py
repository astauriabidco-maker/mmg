from sqlalchemy.orm import Session
from datetime import datetime, date
from .. import models
from ..core.config import STANDARDS, ALERT_THRESHOLD_PERCENT
import csv
import io

class KpiService:
    
    @staticmethod
    def get_daily_logs(db: Session):
        today = date.today()
        start_of_day = datetime.combine(today, datetime.min.time())
        return db.query(models.ProductionLog).filter(
            models.ProductionLog.start_time >= start_of_day
        ).order_by(models.ProductionLog.start_time.desc()).all()

    @staticmethod
    def process_logs(logs):
        processed = []
        alerts = []
        
        for log in logs:
            order_ref = log.order.reference if log.order else f"#{log.order_id}"
            std_min = STANDARDS.get(str(log.station), 30)
            
            if log.end_time:
                real_sec = log.duration_seconds or 0
                real_min = round(real_sec / 60, 1)
            else:
                delta = datetime.now() - log.start_time
                real_sec = delta.total_seconds()
                real_min = round(real_sec / 60, 1)
                
            percent = int((real_min / std_min) * 100) if std_min > 0 else 0
            
            # CSS Logic
            if percent <= 100:
                css_class = "status-green"
            elif percent <= ALERT_THRESHOLD_PERCENT:
                css_class = "status-orange"
            else:
                css_class = "status-red"
            
            entry = {
                "order_ref": order_ref,
                "station": str(log.station),
                "material": log.material or "?",
                "start_str": log.start_time.strftime("%H:%M"),
                "real_min": real_min,
                "std_min": std_min,
                "percent": percent,
                "css_class": css_class,
                "end_time": log.end_time
            }
            
            processed.append(entry)
            
            if percent > ALERT_THRESHOLD_PERCENT:
                alerts.append(entry)
                
        return processed, alerts

    @staticmethod
    def generate_csv_export(db: Session):
        logs = KpiService.get_daily_logs(db)
        processed, _ = KpiService.process_logs(logs)
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Commande", "Poste", "Matiere", "Debut", "Duree (min)", "Standard (min)", "Pourcentage", "Statut"])
        
        for p in processed:
            status = "TERMINE" if p["end_time"] else "EN COURS"
            writer.writerow([
                p["order_ref"], p["station"], p["material"], p["start_str"], 
                p["real_min"], p["std_min"], f"{p['percent']}%", status
            ])
            
        return output.getvalue()

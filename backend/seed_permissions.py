import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import SessionLocal, engine
from backend import models

def seed_permissions():
    db = SessionLocal()
    try:
        permissions = [
            # Comptabilité
            {"code": "ACC_VIEW", "module": "Comptabilité", "description": "Voir le dashboard comptable"},
            {"code": "ACC_EDIT", "module": "Comptabilité", "description": "Gérer les encaissements et factures"},
            # Ventes
            {"code": "SALES_VIEW", "module": "Ventes (CRM)", "description": "Voir les devis et clients"},
            {"code": "SALES_EDIT", "module": "Ventes (CRM)", "description": "Créer et modifier des devis"},
            # Stocks
            {"code": "STOCK_VIEW", "module": "Stocks & Logistique", "description": "Voir l'état des stocks"},
            {"code": "STOCK_EDIT", "module": "Stocks & Logistique", "description": "Gérer les approvisionnements"},
            # Production
            {"code": "PROD_VIEW", "module": "Atelier", "description": "Voir l'Atelier Live"},
            {"code": "PROD_EDIT", "module": "Atelier", "description": "Optimiser et scanner en production"},
            # Configuration
            {"code": "CONF_VIEW", "module": "Configuration", "description": "Accéder aux paramètres de la plateforme"},
        ]

        for p in permissions:
            existing = db.query(models.Permission).filter_by(code=p["code"]).first()
            if not existing:
                db.add(models.Permission(**p))
        
        db.commit()
        print("Initialisation des Permissions terminée avec succès.")

    except Exception as e:
        print(f"Erreur: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_permissions()

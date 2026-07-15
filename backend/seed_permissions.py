import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import SessionLocal, engine
from backend import models

def seed_permissions():
    db = SessionLocal()
    try:
        default_roles = [
            {"name": "SUPER_ADMIN", "description": "Accès total à la plateforme"},
            {"name": "ADMIN", "description": "Administration opérationnelle"},
            {"name": "MANAGER", "description": "Pilotage atelier, ventes et stock"},
            {"name": "SALES", "description": "Avant-vente, CRM et devis"},
            {"name": "OPERATOR", "description": "Opérateur atelier"},
            {"name": "DEBIT_OPERATOR", "description": "Opérateur débit autorisé à consommer les réservations atelier"},
            {"name": "QUALITY_CONTROLLER", "description": "Contrôle qualité atelier"},
            {"name": "WORKSHOP_LEAD", "description": "Chef d'équipe atelier"},
        ]
        for role_data in default_roles:
            existing_role = db.query(models.Role).filter_by(name=role_data["name"]).first()
            if not existing_role:
                db.add(models.Role(**role_data))
        db.commit()

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
            {"code": "planning:start", "module": "Atelier - Actions", "description": "Démarrer une tâche atelier"},
            {"code": "planning:pause", "module": "Atelier - Actions", "description": "Mettre une tâche atelier en pause"},
            {"code": "planning:stop", "module": "Atelier - Actions", "description": "Terminer une tâche atelier"},
            {"code": "planning:consume_stock", "module": "Atelier - Actions", "description": "Consommer le stock réservé au poste débit"},
            {"code": "planning:reprioritize", "module": "Atelier - Pilotage", "description": "Modifier la priorité d'une tâche atelier"},
            {"code": "planning:assign", "module": "Atelier - Pilotage", "description": "Réaffecter une tâche atelier"},
            {"code": "planning:unblock", "module": "Atelier - Pilotage", "description": "Débloquer une tâche atelier"},
            {"code": "planning:report_issue", "module": "Atelier - Actions", "description": "Déclarer un blocage atelier"},
            {"code": "quality:reject", "module": "Atelier - Qualité", "description": "Déclarer un défaut qualité ou renvoyer une pièce"},
            # Configuration
            {"code": "CONF_VIEW", "module": "Configuration", "description": "Accéder aux paramètres de la plateforme"},
        ]

        for p in permissions:
            existing = db.query(models.Permission).filter_by(code=p["code"]).first()
            if not existing:
                db.add(models.Permission(**p))
        
        db.commit()

        default_role_permissions = {
            "OPERATOR": [
                "PROD_VIEW",
                "planning:start",
                "planning:pause",
                "planning:stop",
                "planning:report_issue",
            ],
            "MANAGER": [
                "PROD_VIEW",
                "PROD_EDIT",
                "planning:start",
                "planning:pause",
                "planning:stop",
                "planning:consume_stock",
                "planning:reprioritize",
                "planning:assign",
                "planning:unblock",
                "planning:report_issue",
                "quality:reject",
            ],
            "DEBIT_OPERATOR": [
                "PROD_VIEW",
                "planning:start",
                "planning:pause",
                "planning:stop",
                "planning:consume_stock",
                "planning:report_issue",
            ],
            "QUALITY_CONTROLLER": [
                "PROD_VIEW",
                "planning:start",
                "planning:pause",
                "planning:stop",
                "planning:report_issue",
                "quality:reject",
            ],
            "WORKSHOP_LEAD": [
                "PROD_VIEW",
                "PROD_EDIT",
                "planning:start",
                "planning:pause",
                "planning:stop",
                "planning:consume_stock",
                "planning:reprioritize",
                "planning:assign",
                "planning:unblock",
                "planning:report_issue",
                "quality:reject",
            ],
            "SALES": [
                "SALES_VIEW",
                "SALES_EDIT",
            ],
        }

        for role_name, permission_codes in default_role_permissions.items():
            role = db.query(models.Role).filter_by(name=role_name).first()
            if not role:
                continue
            existing_codes = {permission.code for permission in role.permissions}
            missing_permissions = (
                db.query(models.Permission)
                .filter(models.Permission.code.in_([code for code in permission_codes if code not in existing_codes]))
                .all()
            )
            if missing_permissions:
                role.permissions.extend(missing_permissions)

        db.commit()
        print("Initialisation des Permissions terminée avec succès.")

    except Exception as e:
        print(f"Erreur: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_permissions()

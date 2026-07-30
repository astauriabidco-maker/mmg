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
            {
                "name": "TECHNICO_COMMERCIAL",
                "description": "Pilotage commercial, bureau d'études et consultation/réservation du stock",
            },
            {
                "name": "FINANCE",
                "description": "Comptabilité, facturation, encaissements et lecture financière",
            },
            {"name": "ACHATS", "description": "Commandes fournisseurs, réceptions et rapprochements"},
            {"name": "MAGASINIER", "description": "Réception, rangement, transfert et comptage physique"},
            {"name": "CHEF_STOCK", "description": "Pilotage inventaire, corrections, catalogue et ruptures"},
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
            # Planning transverse
            {"code": "PLANNING_VIEW", "module": "Planning & Agenda", "description": "Voir le planning transverse de l'entreprise"},
            {"code": "PLANNING_EDIT", "module": "Planning & Agenda", "description": "Planifier, affecter et déplacer les actions"},
            {"code": "PLANNING_AVAILABILITY_MANAGE", "module": "Planning & Agenda", "description": "Gérer les horaires individuels et les temps partiels"},
            {"code": "PLANNING_ABSENCE_APPROVE", "module": "Planning & Agenda", "description": "Approuver ou refuser les congés et indisponibilités"},
            {"code": "PLANNING_RESOURCE_MANAGE", "module": "Planning & Agenda", "description": "Gérer les compétences et les ressources planifiables"},
            # Stocks
            {"code": "STOCK_VIEW", "module": "Stocks & Logistique", "description": "Voir l'état des stocks"},
            {"code": "STOCK_EDIT", "module": "Stocks & Logistique", "description": "Gérer les approvisionnements"},
            {"code": "stock.receive", "module": "Stock - Actions", "description": "Réceptionner du stock physique"},
            {"code": "stock.transfer", "module": "Stock - Actions", "description": "Transférer du stock entre emplacements"},
            {"code": "stock.adjust", "module": "Stock - Actions", "description": "Corriger un stock physique avec motif"},
            {"code": "stock.locations.manage", "module": "Stock - Actions", "description": "Créer et structurer les zones et emplacements"},
            {"code": "catalog.qualify", "module": "Stock - Catalogue", "description": "Créer, qualifier et modifier les fiches catalogue"},
            {"code": "workshop.reserve_stock", "module": "Stock - Atelier", "description": "Réserver le stock pour un débit atelier"},
            {"code": "workshop.consume_stock", "module": "Stock - Atelier", "description": "Transformer une réservation atelier en débit réel"},
            {"code": "inventory.count", "module": "Stock - Inventaire physique", "description": "Saisir un comptage physique"},
            {"code": "inventory.validate", "module": "Stock - Inventaire physique", "description": "Valider les écarts d'inventaire"},
            {"code": "inventory.approve_value", "module": "Stock - Inventaire physique", "description": "Approuver les écarts valorisés dépassant le seuil"},
            {"code": "purchases.request", "module": "Achats", "description": "Créer une demande d'achat à valider"},
            {"code": "purchases.approve", "module": "Achats", "description": "Valider ou refuser une demande d'achat"},
            {"code": "purchases.order", "module": "Achats", "description": "Créer un bon de commande fournisseur"},
            {"code": "purchases.receive", "module": "Achats", "description": "Réceptionner une commande fournisseur"},
            {"code": "PURCHASES_VIEW", "module": "Achats", "description": "Consulter les achats et factures fournisseur"},
            {"code": "purchases.invoice.manage", "module": "Achats", "description": "Rapprocher les factures fournisseur"},
            {"code": "purchases.payments.manage", "module": "Achats", "description": "Enregistrer les paiements fournisseur"},
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
                "PLANNING_VIEW",
            ],
            "MANAGER": [
                "ACC_VIEW",
                "ACC_EDIT",
                "SALES_VIEW",
                "SALES_EDIT",
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
                "STOCK_VIEW",
                "STOCK_EDIT",
                "stock.receive",
                "stock.transfer",
                "stock.adjust",
                "stock.locations.manage",
                "catalog.qualify",
                "workshop.reserve_stock",
                "workshop.consume_stock",
                "inventory.count",
                "inventory.validate",
                "inventory.approve_value",
                "purchases.request",
                "purchases.approve",
                "purchases.order",
                "purchases.receive",
                "PURCHASES_VIEW",
                "purchases.invoice.manage",
                "purchases.payments.manage",
                "PLANNING_VIEW",
                "PLANNING_EDIT",
                "PLANNING_AVAILABILITY_MANAGE",
                "PLANNING_ABSENCE_APPROVE",
                "PLANNING_RESOURCE_MANAGE",
            ],
            "DEBIT_OPERATOR": [
                "PROD_VIEW",
                "planning:start",
                "planning:pause",
                "planning:stop",
                "planning:consume_stock",
                "workshop.consume_stock",
                "planning:report_issue",
                "PLANNING_VIEW",
            ],
            "MAGASINIER": [
                "STOCK_VIEW",
                "stock.receive",
                "stock.transfer",
                "inventory.count",
                "purchases.request",
                "purchases.receive",
                "PURCHASES_VIEW",
                "PLANNING_VIEW",
            ],
            "CHEF_STOCK": [
                "STOCK_VIEW",
                "STOCK_EDIT",
                "stock.receive",
                "stock.transfer",
                "stock.adjust",
                "stock.locations.manage",
                "catalog.qualify",
                "workshop.reserve_stock",
                "workshop.consume_stock",
                "inventory.count",
                "inventory.validate",
                "purchases.request",
                "purchases.approve",
                "purchases.order",
                "purchases.receive",
                "PURCHASES_VIEW",
                "purchases.invoice.manage",
                "purchases.payments.manage",
                "PLANNING_VIEW",
                "PLANNING_EDIT",
            ],
            "ACHATS": [
                "STOCK_VIEW",
                "purchases.request",
                "purchases.approve",
                "purchases.order",
                "purchases.receive",
                "PURCHASES_VIEW",
                "purchases.invoice.manage",
                "purchases.payments.manage",
                "PLANNING_VIEW",
            ],
            "QUALITY_CONTROLLER": [
                "PROD_VIEW",
                "planning:start",
                "planning:pause",
                "planning:stop",
                "planning:report_issue",
                "quality:reject",
                "PLANNING_VIEW",
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
                "STOCK_VIEW",
                "stock.receive",
                "stock.transfer",
                "workshop.reserve_stock",
                "workshop.consume_stock",
                "inventory.count",
                "PLANNING_VIEW",
                "PLANNING_EDIT",
                "PLANNING_AVAILABILITY_MANAGE",
                "PLANNING_ABSENCE_APPROVE",
                "PLANNING_RESOURCE_MANAGE",
            ],
            "SALES": [
                "SALES_VIEW",
                "SALES_EDIT",
                "PLANNING_VIEW",
                "PLANNING_EDIT",
            ],
            "TECHNICO_COMMERCIAL": [
                "SALES_VIEW",
                "SALES_EDIT",
                "STOCK_VIEW",
                "workshop.reserve_stock",
                "PLANNING_VIEW",
                "PLANNING_EDIT",
            ],
            "FINANCE": [
                "ACC_VIEW",
                "ACC_EDIT",
                "SALES_VIEW",
                "PURCHASES_VIEW",
                "purchases.invoice.manage",
                "purchases.payments.manage",
                "inventory.approve_value",
                "PLANNING_VIEW",
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

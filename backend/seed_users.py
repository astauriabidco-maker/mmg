import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import SessionLocal, engine
from backend import models
from backend.core.security import get_password_hash

def seed_users():
    db = SessionLocal()
    try:
        # Create Roles
        roles = [
            {"name": "SUPER_ADMIN", "description": "Accès total à la plateforme"},
            {"name": "MANAGER", "description": "Accès à tous les dashboards sauf paramètres avancés"},
            {"name": "SALES", "description": "Accès au CRM et Devis"},
            {"name": "OPERATOR", "description": "Accès limité à l'atelier (Kiosk)"}
        ]

        for r in roles:
            existing = db.query(models.Role).filter_by(name=r["name"]).first()
            if not existing:
                db.add(models.Role(**r))
        
        db.commit()

        # Create Default Users
        users = [
            {"username": "admin", "pin": "1234", "role": "SUPER_ADMIN"},
            {"username": "manager", "pin": "0000", "role": "MANAGER"},
            {"username": "op_debit", "pin": "1111", "role": "OPERATOR"},
            {"username": "op_soudure", "pin": "2222", "role": "OPERATOR"}
        ]

        for u in users:
            existing = db.query(models.User).filter_by(username=u["username"]).first()
            if not existing:
                new_user = models.User(
                    username=u["username"],
                    pin_hash=get_password_hash(u["pin"]),
                    role=u["role"],
                    is_active=True
                )
                db.add(new_user)
        
        db.commit()
        print("Initialisation des Rôles et Utilisateurs terminée avec succès.")

    except Exception as e:
        print(f"Erreur: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    # Create tables if they don't exist
    models.Base.metadata.create_all(bind=engine)
    seed_users()

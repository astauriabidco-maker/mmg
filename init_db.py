from backend.database import engine, SessionLocal
from backend import models
from passlib.context import CryptContext
import os

# Init DB
# Même règle que backend/main.py : create_all est un filet de sécurité en
# développement uniquement. En production, Alembic est la seule source de
# vérité du schéma (appliquée par scripts/docker-entrypoint.sh avant ce script).
if os.environ.get("APP_ENV", "development").lower() != "production":
    models.Base.metadata.create_all(bind=engine)

# Password Hasher
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def init():
    db = SessionLocal()
    app_env = os.environ.get("APP_ENV", "development").lower()
    admin_username = os.environ.get("ADMIN_USERNAME", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD", "1234")
    if app_env == "production" and (admin_password == "1234" or admin_password.startswith("CHANGE_ME")):
        raise RuntimeError("ADMIN_PASSWORD must be set to a non-default value when APP_ENV=production")
    
    # Check if admin exists
    admin = db.query(models.User).filter(models.User.username == admin_username).first()
    if not admin:
        print("Creating Admin User...")
        hashed_pin = pwd_context.hash(admin_password)
        admin_user = models.User(username=admin_username, pin_hash=hashed_pin, role=models.UserRole.ADMIN)
        db.add(admin_user)
        db.commit()
        print(f"Admin user created ({admin_username})")
    else:
        print("Admin user already exists.")
        
    db.close()
    from backend.seed_permissions import seed_permissions
    seed_permissions()

if __name__ == "__main__":
    init()

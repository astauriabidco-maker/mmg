from backend.database import engine, SessionLocal
from backend import models
from passlib.context import CryptContext

# Init DB
models.Base.metadata.create_all(bind=engine)

# Password Hasher
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def init():
    db = SessionLocal()
    
    # Check if admin exists
    admin = db.query(models.User).filter(models.User.username == "admin").first()
    if not admin:
        print("Creating Admin User...")
        hashed_pin = pwd_context.hash("1234")
        admin_user = models.User(username="admin", pin_hash=hashed_pin, role=models.UserRole.ADMIN)
        db.add(admin_user)
        db.commit()
        print("Admin user created (PIN: 1234)")
    else:
        print("Admin user already exists.")
        
    db.close()

if __name__ == "__main__":
    init()

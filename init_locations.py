from backend.database import SessionLocal, engine
from backend import models

print("Création des nouvelles tables manquantes (StorageLocation)...")
models.Base.metadata.create_all(bind=engine)
print("Création réussie !")

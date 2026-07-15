from sqlalchemy.orm import Session
from backend.database import SessionLocal, engine
from backend import models

DEFAULT_STATIONS = [
        ("PVC_DEBIT", "Débit PVC", "PVC", 10),
        ("PVC_SOUDURE", "Soudure PVC", "PVC", 20),
        ("PVC_ASSEMBLAGE", "Assemblage PVC", "PVC", 30),
        ("PVC_VITRAGE", "Vitrage PVC", "PVC", 40),
        ("PVC_CONTROLE", "Contrôle PVC", "PVC", 50),
        ("PVC_EMBALLAGE", "Emballage PVC", "PVC", 60),
        ("ALU_DEBIT", "Débit ALU", "ALU", 10),
        ("ALU_USINAGE", "Usinage ALU", "ALU", 20),
        ("ALU_ASSEMBLAGE", "Assemblage ALU", "ALU", 30),
        ("ALU_VITRAGE", "Vitrage ALU", "ALU", 40),
        ("ALU_CONTROLE", "Contrôle ALU", "ALU", 50),
        ("ALU_EMBALLAGE", "Emballage ALU", "ALU", 60),
]


def seed_default_stations(db: Session, verbose: bool = False):
    created = 0
    for code, name, mat, idx in DEFAULT_STATIONS:
        exists = db.query(models.Station).filter(models.Station.code == code).first()
        if not exists:
            db.add(models.Station(
                code=code,
                display_name=name,
                material=models.MaterialType(mat),
                order_index=idx
            ))
            created += 1
            if verbose:
                print(f"Added station: {code}")
    return created


def ensure_default_stations():
    db = SessionLocal()
    try:
        if seed_default_stations(db) > 0:
            db.commit()
    finally:
        db.close()


def seed():
    db = SessionLocal()
    seed_default_stations(db, verbose=True)
    db.commit()
    db.close()

if __name__ == "__main__":
    seed()

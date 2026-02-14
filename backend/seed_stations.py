from sqlalchemy.orm import Session
from backend.database import SessionLocal, engine
from backend import models

def seed():
    db = SessionLocal()
    
    # PVC Stations
    pvc_stations = [
        ("PVC_DEBIT", "Débit PVC", "PVC", 10),
        ("PVC_SOUDURE", "Soudure PVC", "PVC", 20),
        ("PVC_ASSEMBLAGE", "Assemblage PVC", "PVC", 30),
        ("PVC_VITRAGE", "Vitrage PVC", "PVC", 40),
        ("PVC_CONTROLE", "Contrôle PVC", "PVC", 50),
    ]
    
    # ALU Stations
    alu_stations = [
        ("ALU_DEBIT", "Débit ALU", "ALU", 10),
        ("ALU_USINAGE", "Usinage ALU", "ALU", 20),
        ("ALU_ASSEMBLAGE", "Assemblage ALU", "ALU", 30),
        ("ALU_VITRAGE", "Vitrage ALU", "ALU", 40),
        ("ALU_CONTROLE", "Contrôle ALU", "ALU", 50),
    ]
    
    for code, name, mat, idx in pvc_stations + alu_stations:
        exists = db.query(models.Station).filter(models.Station.code == code).first()
        if not exists:
            db.add(models.Station(
                code=code,
                display_name=name,
                material=models.MaterialType(mat),
                order_index=idx
            ))
            print(f"Added station: {code}")
    
    db.commit()
    db.close()

if __name__ == "__main__":
    seed()

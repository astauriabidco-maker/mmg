from backend.database import SessionLocal, engine
from backend import models

def seed_stock():
    models.Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    print("--- Seeding Initial Stock ---")

    items = [
        {
            "reference": "PVC-MAIN-PROFILE",
            "name": "Profilé Principal PVC Blanc 70mm",
            "material_type": "PVC",
            "quantity_in_stock": 50.5,
            "unit": "ml",
            "min_threshold": 100.0 # Intentional alert
        },
        {
            "reference": "ALU-MAIN-PROFILE",
            "name": "Profilé Principal ALU Noir Mat",
            "material_type": "ALU",
            "quantity_in_stock": 420.0,
            "unit": "ml",
            "min_threshold": 50.0
        },
        {
            "reference": "GLASS-4-16-4",
            "name": "Vitrage Double 4/16/4 Clair",
            "material_type": "VITRAGE",
            "quantity_in_stock": 15.0,
            "unit": "m2",
            "min_threshold": 20.0 # Intentional alert
        },
        {
            "reference": "HW-HANDLE-W",
            "name": "Poignée Secustik Blanche",
            "material_type": "ACCESSOIRE",
            "quantity_in_stock": 150.0,
            "unit": "pce",
            "min_threshold": 50.0
        }
    ]

    for item_data in items:
        existing = db.query(models.StockItem).filter_by(reference=item_data["reference"]).first()
        if not existing:
            new_item = models.StockItem(**item_data)
            db.add(new_item)
            
    db.commit()
    print("Stock seeded successfully!")
    db.close()

if __name__ == "__main__":
    seed_stock()

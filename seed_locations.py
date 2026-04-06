from backend.database import SessionLocal
from backend.models import StockLocation

db = SessionLocal()

# Check if locations exist
supplier = db.query(StockLocation).filter_by(usage="supplier").first()
if not supplier:
    db.add(StockLocation(name="Fournisseur (Achats)", usage="supplier"))

inventory = db.query(StockLocation).filter_by(usage="inventory").first()
if not inventory:
    db.add(StockLocation(name="Perte / Ajustement (Casse)", usage="inventory"))

production = db.query(StockLocation).filter_by(usage="production").first()
if not production:
    db.add(StockLocation(name="Production (Consommation)", usage="production"))

customer = db.query(StockLocation).filter_by(usage="customer").first()
if not customer:
    db.add(StockLocation(name="Client (Livraison)", usage="customer"))

internal = db.query(StockLocation).filter_by(usage="internal").first()
if not internal:
    db.add(StockLocation(name="Dépôt Principal (Stock)", usage="internal"))

db.commit()
print("Locations Seeded successfully.")

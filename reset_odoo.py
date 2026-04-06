import sqlite3
from sqlalchemy.orm import Session
from backend.database import SessionLocal, engine
from backend import models

def run():
    print("Mise à niveau de la base de données vers une architecture Double-Entrée (Odoo)...")
    try:
        c = engine.raw_connection().cursor()
        c.execute("DROP TABLE IF EXISTS stock_transactions")
        c.execute("DROP TABLE IF EXISTS storage_locations")
        c.execute("DROP TABLE IF EXISTS stock_moves")
        c.execute("DROP TABLE IF EXISTS stock_quants")
        c.execute("DROP TABLE IF EXISTS stock_locations")
        c.connection.commit()
        c.close()
    except Exception as e:
        print("Erreur DROP:", e)

    models.Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    supplier_loc = models.StockLocation(id=1, name="Vendor / Fournisseurs", usage="supplier", parent_id=None)
    inventory_loc = models.StockLocation(id=2, name="Ajustement d'inventaire", usage="inventory", parent_id=None)
    wh_loc = models.StockLocation(id=3, name="WH / Magasin Principal", usage="internal", parent_id=None)

    db.add(supplier_loc)
    db.add(inventory_loc)
    db.add(wh_loc)
    db.commit()

    print("Emplacements virtuels et physiques créés.")

    # Convert existing variants to Quants if they have stock
    variants = db.query(models.ProductVariant).all()
    count = 0
    for v in variants:
        if v.quantity_in_stock and v.quantity_in_stock > 0:
            db.add(models.StockQuant(variant_id=v.id, location_id=wh_loc.id, quantity=v.quantity_in_stock))
            import time
            db.add(models.StockMove(
                reference=f"WH/IN/{int(time.time()*1000)}",
                variant_id=v.id,
                location_id=inventory_loc.id,
                location_dest_id=wh_loc.id,
                quantity=v.quantity_in_stock,
                notes="Migration du stock existant"
            ))
            count += 1
            
    db.commit()
    db.close()
    print(f"Migration Odoo réussie ! {count} stocks convertis en Quants et Mouvements certifiés.")

if __name__ == "__main__":
    run()

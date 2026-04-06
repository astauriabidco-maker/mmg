import sqlite3
def run():
    conn = sqlite3.connect("atelier.db")
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS storage_locations")
    conn.commit()
    conn.close()
    
    from backend.database import SessionLocal, engine
    from backend import models
    models.Base.metadata.create_all(bind=engine)
    print("Table storage_locations recréée avec le support hiérarchique ! 🌲")
if __name__ == "__main__":
    run()

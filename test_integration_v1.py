import unittest
import os
import shutil
import json
import time
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Imports modules internes
from backend import main, models, database, extractor, qr_generator

# Setup Test Env
TEST_DB_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

main.app.dependency_overrides[main.get_db] = override_get_db
models.Base.metadata.create_all(bind=engine)
client = TestClient(main.app)

class TestIntegrationV1(unittest.TestCase):
    def setUp(self):
        # Reset DB
        models.Base.metadata.drop_all(bind=engine)
        models.Base.metadata.create_all(bind=engine)
        
        # Setup Output Dirs
        os.makedirs("output/test_integration", exist_ok=True)
        self.pdf_path = "output/test_integration/test_cmd.pdf"

    def tearDown(self):
        if os.path.exists("output/test_integration"):
            shutil.rmtree("output/test_integration")

    def test_full_flow(self):
        print("\n--- TEST INTEGRATION V1 START ---")

        # 1. SIMULATION EXTRACTION (Module Independent)
        # On ne teste pas le Watcher en boucle infinie, mais l'Extractor
        print("[1] Simulation Extraction PDF...")
        # Simuler un fichier PDF (Mock du contenu texte pour l'extractor natif qui lit le fichier)
        # Difficile de créer un vrai PDF valide vite fait sans reportlab, mais on a reportlab !
        from reportlab.pdfgen import canvas
        c = canvas.Canvas(self.pdf_path)
        c.drawString(100, 100, "Ref: CMD-INTEG-01")
        c.drawString(100, 80, "Largeur: 1200")
        c.drawString(100, 60, "Hauteur: 2000")
        c.drawString(100, 40, "Matière: ALU")
        c.save()
        
        # Run Extractor
        ext = extractor.PDFExtractor()
        data = ext.process(self.pdf_path)
        self.assertEqual(data["reference"], "CMD-INTEG-01")
        self.assertEqual(data["material"], "ALU")
        print("    > Extraction OK")

        # 2. GENERATION QR
        print("[2] Génération Etiquette QR...")
        qr_path = qr_generator.generate_label(data)
        self.assertTrue(os.path.exists(qr_path))
        print(f"    > QR Generated at {qr_path}")

        # 3. CREATION ORDER (Backend Requirement for FK)
        # L'extractor normal appelle l'API pour créer l'ordre, ici on le fait via Client
        print("[3] Création Ordre en BDD...")
        order_payload = {
            "reference": data["reference"],
            "width": data["width_mm"],
            "height": data["height_mm"],
            "material": data["material"]
        }
        resp = client.post("/orders/", json=order_payload)
        self.assertEqual(resp.status_code, 200)
        print("    > Ordre créé via API")

        # 4. SIMULATION APP ANDROID (Sync REST)
        print("[4] Simulation Scan & Prod (Android)...")
        # START
        start_payload = {"order_reference": "CMD-INTEG-01", "station": "ALU_DEBIT"}
        resp = client.post("/production/start", json=start_payload)
        self.assertEqual(resp.status_code, 200)
        print("    > Production Started")
        
        # Wait simulated duration? No, just timestamp manipulation logic inside app usually, 
        # but here backend sets timestamp.
        # We can simulate a sleep or just immediate stop for test.
        time.sleep(0.1) 
        
        # STOP
        resp = client.post("/production/stop", json=start_payload)
        self.assertEqual(resp.status_code, 200)
        log_data = resp.json()
        self.assertIsNotNone(log_data["end_time"])
        print(f"    > Production Stopped (Duration: {log_data['duration_seconds']}s)")

        # 5. DASHBOARD METRICS
        print("[5] Vérification Dashboard...")
        resp = client.get("/dashboard/metrics")
        metrics = resp.json()
        
        # Check KPI
        # Active orders = 0 (we just stopped it)
        self.assertEqual(metrics["kpi"]["active_orders"], 0)
        # Global Avg should exist
        self.assertGreater(metrics["kpi"]["global_avg_seconds"], 0)
        
        # Check ALU Section
        found_alu = False
        for station in metrics["alu"]:
            if station["station"] == "ALU_DEBIT":
                found_alu = True
                self.assertGreater(station["avg_seconds"], 0)
        self.assertTrue(found_alu)
        
        print("    > Dashboard Metrics OK")

        print("--- TEST INTEGRATION V1 SUCCESS ---")

if __name__ == "__main__":
    unittest.main()

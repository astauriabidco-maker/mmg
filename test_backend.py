from fastapi.testclient import TestClient
from backend.main import app, get_db
from backend import models, database
import datetime

# Use in-memory SQLite
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
models.Base.metadata.create_all(bind=engine)

client = TestClient(app)

def test_sprint1_workflow():
    print("Starting Sprint 1 Test Workflow...")
    
    # 1. Create Order (Setup)
    order_data = {
        "reference": "CMD-SPRINT1",
        "width": 1000,
        "height": 2000,
        "material": "PVC"
    }
    client.post("/orders/", json=order_data)

    # 2. START Production
    start_payload = {
        "order_reference": "CMD-SPRINT1",
        "station": "PVC_DEBIT"
    }
    response = client.post("/production/start", json=start_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["station"] == "PVC_DEBIT"
    assert data["start_time"] is not None
    assert data["end_time"] is None
    print("Production Start: OK")

    # 3. STOP Production
    stop_payload = {
        "order_reference": "CMD-SPRINT1",
        "station": "PVC_DEBIT"
    }
    # Simulate time passing? No, just call stop
    response = client.post("/production/stop", json=stop_payload)
    if response.status_code != 200:
        print(f"Stop Failed: {response.text}")
    assert response.status_code == 200
    data = response.json()
    assert data["end_time"] is not None
    assert data["duration_seconds"] is not None
    print("Production Stop: OK")

    # 4. Dashboard Summary
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["total_orders"] == 1
    assert data["total_production_time"] >= 0
    print("Dashboard Summary: OK")

    print("ALL SPRINT 1 TESTS PASSED")

if __name__ == "__main__":
    try:
        test_sprint1_workflow()
    except Exception as e:
        print(f"TEST FAILED: {e}")
        exit(1)

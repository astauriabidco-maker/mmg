from fastapi.testclient import TestClient
from backend.main import app, get_db
from backend import models, database
import datetime

# Use in-memory SQLite for reliable testing
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

def test_dashboard_stats():
    # 1. Create dummy data
    db = TestingSessionLocal()
    order = models.Order(reference="CMD-DASH", width=100, height=100, material="PVC")
    db.add(order)
    db.commit()
    db.refresh(order)
    
    # Log 1: PVC_DEBIT, 300s (Standard)
    log1 = models.TimeLog(
        order_id=order.id, 
        station="PVC_DEBIT", 
        start_time=datetime.datetime.now(), 
        duration_seconds=300
    )
    # Log 2: PVC_DEBIT, 600s (200% Standard -> Alert)
    log2 = models.TimeLog(
        order_id=order.id, 
        station="PVC_DEBIT", 
        start_time=datetime.datetime.now(), 
        duration_seconds=600
    )
    db.add_all([log1, log2])
    db.commit()
    db.close()

    # 2. Call Dashboard API
    response = client.get("/stats/dashboard")
    assert response.status_code == 200
    data = response.json()
    
    print("Dashboard Data:", data)
    
    assert data["total_orders"] == 1
    assert data["total_seconds"] == 900
    
    # Check Stations
    stations = {s["name"]: s for s in data["stations"]}
    assert "PVC_DEBIT" in stations
    pvc_debit = stations["PVC_DEBIT"]
    assert pvc_debit["count"] == 2
    assert pvc_debit["avg_duration"] == 450.0
    assert pvc_debit["standard"] == 300

    print("DASHBOARD TEST PASSED")

if __name__ == "__main__":
    try:
        test_dashboard_stats()
    except Exception as e:
        print(f"TEST FAILED: {e}")
        exit(1)

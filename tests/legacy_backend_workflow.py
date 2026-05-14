import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import time

# Import app logic
from backend.main import app, get_db
from backend import models

# --- SETUP MOCK DB ---
TEST_DB_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

# --- CONFIG TEST ---
TEST_ORDER = "CMD-TEST-001"
WORKSTATION = "PVC_DEBIT"
OPERATOR = "001"

@pytest.fixture(scope="module", autouse=True)
def init_db():
    models.Base.metadata.create_all(bind=engine)
    # Create Test Order
    client.post("/orders/", json={
        "reference": TEST_ORDER,
        "width": 1000,
        "height": 1000,
        "material": "PVC"
    })
    yield
    models.Base.metadata.drop_all(bind=engine)

def test_start_production():
    # Attempt to stop just in case (Logique script user)
    client.post("/production/stop", json={
        "order_reference": TEST_ORDER,
        "station": WORKSTATION
    })

    # START
    response = client.post("/production/start", json={
        "order_reference": TEST_ORDER,
        "station": WORKSTATION,
        "material_type": "PVC",
        "operator_pin": OPERATOR
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["station"] == WORKSTATION
    assert data["start_time"] is not None

def test_double_start_blocked():
    # Should be already started
    response = client.post("/production/start", json={
        "order_reference": TEST_ORDER,
        "station": WORKSTATION
    })

    # PROGES V1 Rule: Block double start
    assert response.status_code == 400
    assert "already active" in response.json()["detail"].lower()

def test_stop_production():
    # Simulate work
    # Note: TestClient is fast, timestamps might be identical if no sleep
    # But db resolution usually supports microsecond.
    # We rely on previous steps having started it.
    
    response = client.post("/production/stop", json={
        "order_reference": TEST_ORDER,
        "station": WORKSTATION
    })

    assert response.status_code == 200
    data = response.json()
    assert data["end_time"] is not None
    # duration might be 0.0 if too fast, but key must exist
    assert "duration_seconds" in data

def test_dashboard_summary():
    response = client.get("/dashboard/summary")

    assert response.status_code == 200
    data = response.json()

    # Verify keys asked by user
    assert "total_orders" in data
    assert "average_duration" in data
    assert "over_120_percent" in data
    # Verify values logic (1 finished order)
    assert data["total_orders"] >= 1

def test_multiple_orders_simulation():
    # Simuler 30 commandes
    for i in range(30):
        order_ref = f"CMD-SIM-{i}"
        
        # 1. Create Order
        client.post("/orders/", json={
            "reference": order_ref,
            "width": 500 + i,
            "height": 500 + i,
            "material": "ALU"
        })

        # 2. Start
        r_start = client.post("/production/start", json={
            "order_reference": order_ref,
            "station": "ALU_USINAGE",
            "material_type": "ALU",
            "operator_pin": "002"
        })
        assert r_start.status_code == 200

        # 3. Stop
        r_stop = client.post("/production/stop", json={
            "order_reference": order_ref,
            "station": "ALU_USINAGE"
        })
        assert r_stop.status_code == 200

    # Check Dashboard again
    r_dash = client.get("/dashboard/summary")
    assert r_dash.status_code == 200
    d_data = r_dash.json()
    assert d_data["total_orders"] >= 31 # 1 initial + 30 sim

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def test_workshop_flow_updates_order_tracking_without_500():
    from backend import database, models
    from backend.core import security
    from backend.main import app, get_db
    from backend.seed_stations import seed_default_stations

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    def override_current_user():
        return {"sub": "atelier-admin", "role": "ADMIN", "stations": ["PVC_DEBIT"]}

    def override_current_user_role():
        return "ADMIN"

    def override_current_user_roles():
        return ["ADMIN"]

    models.Base.metadata.create_all(bind=engine)
    with testing_session_local() as db:
        seed_default_stations(db)
        db.commit()

    app.dependency_overrides[database.get_db] = override_get_db
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[security.get_current_user] = override_current_user
    app.dependency_overrides[security.get_current_user_role] = override_current_user_role
    app.dependency_overrides[security.get_current_user_roles] = override_current_user_roles

    try:
        client = TestClient(app)
        order_reference = "CMD-E2E-ATELIER-001"
        station = "PVC_DEBIT"

        ingest_response = client.post(
            "/v2/ingest/order",
            json={
                "reference": order_reference,
                "width": 1200,
                "height": 900,
                "material": "PVC",
                "client_name": "Client Atelier",
                "color": "Blanc",
                "quantity": 1,
                "system_type": "Coulissant",
            },
        )
        assert ingest_response.status_code == 200

        queue_response = client.get(f"/v2/planning/{station}")
        assert queue_response.status_code == 200
        planning_items = queue_response.json()
        assert any(item["order_reference"] == order_reference for item in planning_items)

        start_response = client.post(
            "/production/start",
            json={"order_reference": order_reference, "station": station},
        )
        assert start_response.status_code == 200

        tracking_response = client.get("/v2/ingest/orders/tracking")
        assert tracking_response.status_code == 200
        tracked_order = _tracked_order(tracking_response.json(), order_reference)
        assert tracked_order["status"] == "IN_PROGRESS"
        assert tracked_order["current_station"] == station
        assert tracked_order["steps"] == [{"station": station, "status": "IN_PROGRESS"}]

        stop_response = client.post(
            "/production/stop",
            json={"order_reference": order_reference, "station": station},
        )
        assert stop_response.status_code == 200

        final_tracking_response = client.get("/v2/ingest/orders/tracking")
        assert final_tracking_response.status_code == 200
        tracked_order = _tracked_order(final_tracking_response.json(), order_reference)
        assert tracked_order["status"] == "READY"
        assert tracked_order["progress"] == 100
        assert tracked_order["current_station"] is None
        assert tracked_order["steps"] == [{"station": station, "status": "DONE"}]
    finally:
        app.dependency_overrides.clear()
        models.Base.metadata.drop_all(bind=engine)


def _tracked_order(orders, reference):
    for order in orders:
        if order["reference"] == reference:
            return order
    raise AssertionError(f"Order {reference} not found in tracking response")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import database, models
from backend.core import security
from backend.main import app


def _client_with_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[database.get_db] = override_get_db
    token = security.create_access_token({"sub": "inventory-tester", "role": "ADMIN"})
    return TestClient(app), TestingSessionLocal, engine, {"Authorization": f"Bearer {token}"}


def test_physical_inventory_validation_creates_adjustment_move():
    client, TestingSessionLocal, engine, headers = _client_with_db()
    try:
        product_response = client.post(
            "/v2/stock/products",
            headers=headers,
            json={
                "reference_base": "INV-COUNT-PROD",
                "name": "Profil inventaire",
                "material_type": "ALU",
                "unit": "barre",
                "supplier": "MMG",
                "variants": [
                    {
                        "reference": "INV-COUNT-PROD-001",
                        "color": "Std",
                        "cost_price": 25,
                        "quantity_in_stock": 0,
                        "min_threshold": 2,
                    }
                ],
            },
        )
        assert product_response.status_code == 200, product_response.text
        variant_id = product_response.json()["variants"][0]["id"]

        location_response = client.post(
            "/v2/stock/locations",
            headers=headers,
            json={"name": "WH/Inventaire Test", "usage": "internal"},
        )
        assert location_response.status_code == 200, location_response.text
        location_id = location_response.json()["id"]

        initial_move = client.post(
            "/v2/stock/transaction",
            headers=headers,
            json={
                "variant_id": variant_id,
                "location_dest_id": location_id,
                "quantity": 10,
                "notes": "Stock initial test",
            },
        )
        assert initial_move.status_code == 200, initial_move.text

        session_response = client.post(
            "/v2/stock/inventory-sessions",
            headers=headers,
            json={
                "name": "Comptage test",
                "location_id": location_id,
                "notes": "Campagne test",
            },
        )
        assert session_response.status_code == 200, session_response.text
        session_id = session_response.json()["id"]
        assert session_response.json()["status"] == "draft"

        line_response = client.post(
            f"/v2/stock/inventory-sessions/{session_id}/lines",
            headers=headers,
            json={
                "variant_id": variant_id,
                "location_id": location_id,
                "counted_quantity": 7,
                "reason": "Casse atelier constatée",
            },
        )
        assert line_response.status_code == 200, line_response.text
        line = line_response.json()
        assert line["expected_quantity"] == 10.0
        assert line["counted_quantity"] == 7.0
        assert line["variance_quantity"] == -3.0

        validate_response = client.post(
            f"/v2/stock/inventory-sessions/{session_id}/validate",
            headers=headers,
        )
        assert validate_response.status_code == 200, validate_response.text
        validated = validate_response.json()
        assert validated["status"] == "validated"
        assert validated["validated_by"] == "inventory-tester"
        assert validated["lines"][0]["adjustment_move_id"] is not None

        with TestingSessionLocal() as db:
            quant = db.query(models.StockQuant).filter_by(variant_id=variant_id, location_id=location_id).one()
            variant = db.query(models.ProductVariant).filter_by(id=variant_id).one()
            inventory_location = db.query(models.StockLocation).filter_by(name="Virtual/Inventory", usage="inventory").one()
            adjustment_move = (
                db.query(models.StockMove)
                .filter(models.StockMove.reference.like(f"INV/{validated['reference']}/%"))
                .one()
            )
            inventory_quant = (
                db.query(models.StockQuant)
                .filter_by(variant_id=variant_id, location_id=inventory_location.id)
                .one()
            )

        assert quant.quantity == 7.0
        assert variant.quantity_in_stock == 7.0
        assert inventory_quant.quantity == 3.0
        assert adjustment_move.location_id == location_id
        assert adjustment_move.location_dest_id == inventory_location.id
        assert adjustment_move.quantity == 3.0
        assert "Casse atelier constatée" in adjustment_move.notes
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def test_physical_inventory_validation_blocks_if_stock_changed_after_count():
    client, TestingSessionLocal, engine, headers = _client_with_db()
    try:
        product_response = client.post(
            "/v2/stock/products",
            headers=headers,
            json={
                "reference_base": "INV-CONFLICT-PROD",
                "name": "Profil conflit",
                "material_type": "ALU",
                "unit": "barre",
                "supplier": "MMG",
                "variants": [{"reference": "INV-CONFLICT-PROD-001", "quantity_in_stock": 0}],
            },
        )
        assert product_response.status_code == 200, product_response.text
        variant_id = product_response.json()["variants"][0]["id"]

        location_response = client.post(
            "/v2/stock/locations",
            headers=headers,
            json={"name": "WH/Inventaire Conflit", "usage": "internal"},
        )
        assert location_response.status_code == 200, location_response.text
        location_id = location_response.json()["id"]

        assert client.post(
            "/v2/stock/transaction",
            headers=headers,
            json={"variant_id": variant_id, "location_dest_id": location_id, "quantity": 5},
        ).status_code == 200

        session_response = client.post(
            "/v2/stock/inventory-sessions",
            headers=headers,
            json={"name": "Comptage conflit", "location_id": location_id},
        )
        assert session_response.status_code == 200, session_response.text
        session_id = session_response.json()["id"]

        assert client.post(
            f"/v2/stock/inventory-sessions/{session_id}/lines",
            headers=headers,
            json={"variant_id": variant_id, "location_id": location_id, "counted_quantity": 4},
        ).status_code == 200

        assert client.post(
            "/v2/stock/transaction",
            headers=headers,
            json={"variant_id": variant_id, "location_dest_id": location_id, "quantity": 1},
        ).status_code == 200

        validate_response = client.post(
            f"/v2/stock/inventory-sessions/{session_id}/validate",
            headers=headers,
        )
        assert validate_response.status_code == 409, validate_response.text
        assert "Stock modifié depuis le comptage" in validate_response.json()["detail"]
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)

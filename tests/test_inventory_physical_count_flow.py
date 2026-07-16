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
        assert session_response.json()["zone_locked"] is True

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
        assert line["status"] == "variance"

        validate_response = client.post(
            f"/v2/stock/inventory-sessions/{session_id}/validate",
            headers=headers,
        )
        assert validate_response.status_code == 200, validate_response.text
        validated = validate_response.json()
        assert validated["status"] == "validated"
        assert validated["validated_by"] == "inventory-tester"
        assert validated["zone_locked"] is False
        assert validated["lines"][0]["status"] == "validated"
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


def test_physical_inventory_session_locks_zone_until_cancelled():
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

        locked_move = client.post(
            "/v2/stock/transaction",
            headers=headers,
            json={"variant_id": variant_id, "location_dest_id": location_id, "quantity": 1},
        )
        assert locked_move.status_code == 423, locked_move.text
        assert "Zone gelée" in locked_move.json()["detail"]

        cancel_response = client.post(
            f"/v2/stock/inventory-sessions/{session_id}/cancel",
            headers=headers,
        )
        assert cancel_response.status_code == 200, cancel_response.text
        assert cancel_response.json()["status"] == "cancelled"
        assert cancel_response.json()["zone_locked"] is False

        unlocked_move = client.post(
            "/v2/stock/transaction",
            headers=headers,
            json={"variant_id": variant_id, "location_dest_id": location_id, "quantity": 1},
        )
        assert unlocked_move.status_code == 200, unlocked_move.text
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def test_physical_inventory_recount_blocks_validation_and_export_report():
    client, TestingSessionLocal, engine, headers = _client_with_db()
    try:
        product_response = client.post(
            "/v2/stock/products",
            headers=headers,
            json={
                "reference_base": "INV-RECOUNT-PROD",
                "name": "Profil recompte",
                "material_type": "ALU",
                "unit": "barre",
                "supplier": "MMG",
                "variants": [{"reference": "INV-RECOUNT-PROD-001", "quantity_in_stock": 0}],
            },
        )
        assert product_response.status_code == 200, product_response.text
        variant_id = product_response.json()["variants"][0]["id"]

        location_response = client.post(
            "/v2/stock/locations",
            headers=headers,
            json={"name": "WH/Inventaire Recompte", "usage": "internal"},
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
            json={"name": "Comptage recompte", "location_id": location_id},
        )
        assert session_response.status_code == 200, session_response.text
        session_id = session_response.json()["id"]

        line_response = client.post(
            f"/v2/stock/inventory-sessions/{session_id}/lines",
            headers=headers,
            json={"variant_id": variant_id, "location_id": location_id, "counted_quantity": 4, "reason": "Écart à confirmer"},
        )
        assert line_response.status_code == 200, line_response.text
        line_id = line_response.json()["id"]

        recount_response = client.post(
            f"/v2/stock/inventory-sessions/{session_id}/lines/{line_id}/recount",
            headers=headers,
            json={"notes": "Deuxième opérateur requis"},
        )
        assert recount_response.status_code == 200, recount_response.text
        assert recount_response.json()["status"] == "recount"

        blocked_validate = client.post(
            f"/v2/stock/inventory-sessions/{session_id}/validate",
            headers=headers,
        )
        assert blocked_validate.status_code == 400, blocked_validate.text
        assert "attente de recompte" in blocked_validate.json()["detail"]

        export_response = client.get(
            f"/v2/stock/inventory-sessions/{session_id}/export",
            headers=headers,
        )
        assert export_response.status_code == 200, export_response.text
        assert export_response.content.startswith(b"PK")
        assert "spreadsheetml.sheet" in export_response.headers["content-type"]

        recount_line = client.post(
            f"/v2/stock/inventory-sessions/{session_id}/lines",
            headers=headers,
            json={"variant_id": variant_id, "location_id": location_id, "counted_quantity": 5},
        )
        assert recount_line.status_code == 200, recount_line.text
        assert recount_line.json()["status"] == "ok"

        validate_response = client.post(
            f"/v2/stock/inventory-sessions/{session_id}/validate",
            headers=headers,
        )
        assert validate_response.status_code == 200, validate_response.text
        assert validate_response.json()["status"] == "validated"
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)

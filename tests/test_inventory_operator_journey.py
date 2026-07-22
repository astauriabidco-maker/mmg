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
    with TestingSessionLocal() as db:
        db.add(models.User(username="operator-journey", pin_hash="test-pin", role="ADMIN", is_active=True))
        db.commit()
    token = security.create_access_token({"sub": "operator-journey", "role": "ADMIN"})
    return TestClient(app), TestingSessionLocal, engine, {"Authorization": f"Bearer {token}"}


def test_inventory_operator_journey_catalog_locations_receipt_transfer_count_audit():
    client, TestingSessionLocal, engine, headers = _client_with_db()
    try:
        product_response = client.post(
            "/v2/stock/products",
            headers=headers,
            json={
                "reference_base": "OP-JOURNEY-001",
                "name": "Article parcours opérateur",
                "material_type": "ACCESSOIRE",
                "unit": "pce",
                "supplier": "MMG",
                "product_type": "stockable",
                "catalog_status": "ACTIVE",
                "variants": [
                    {
                        "reference": "OP-JOURNEY-001-STD",
                        "cost_price": 15,
                        "quantity_in_stock": 0,
                        "min_threshold": 2,
                    }
                ],
            },
        )
        assert product_response.status_code == 200, product_response.text
        product = product_response.json()
        product_id = product["id"]
        variant_id = product["variants"][0]["id"]

        update_response = client.put(
            f"/v2/stock/products/{product_id}",
            headers=headers,
            json={
                "reference_base": "OP-JOURNEY-001",
                "name": "Article parcours opérateur modifié",
                "material_type": "ACCESSOIRE",
                "unit": "pce",
                "supplier": "MMG",
                "product_type": "stockable",
                "available_in_pos": False,
                "catalog_status": "ACTIVE",
            },
        )
        assert update_response.status_code == 200, update_response.text
        assert update_response.json()["name"] == "Article parcours opérateur modifié"

        warehouse_response = client.post(
            "/v2/stock/locations",
            headers=headers,
            json={"name": "TEST/Entrepôt opérateur", "usage": "internal"},
        )
        assert warehouse_response.status_code == 200, warehouse_response.text
        warehouse_id = warehouse_response.json()["id"]

        rack_response = client.post(
            "/v2/stock/locations",
            headers=headers,
            json={"name": "Rack A", "usage": "internal", "parent_id": warehouse_id},
        )
        assert rack_response.status_code == 200, rack_response.text
        rack_id = rack_response.json()["id"]
        assert rack_response.json()["parent_id"] == warehouse_id

        transfer_zone_response = client.post(
            "/v2/stock/locations",
            headers=headers,
            json={"name": "Rack B", "usage": "internal", "parent_id": warehouse_id},
        )
        assert transfer_zone_response.status_code == 200, transfer_zone_response.text
        rack_b_id = transfer_zone_response.json()["id"]

        locations_response = client.get("/v2/stock/locations", headers=headers)
        assert locations_response.status_code == 200, locations_response.text
        location_names = {location["name"] for location in locations_response.json()}
        assert {"TEST/Entrepôt opérateur", "Rack A", "Rack B"}.issubset(location_names)

        receipt_response = client.post(
            "/v2/stock/transaction",
            headers=headers,
            json={
                "variant_id": variant_id,
                "location_dest_id": rack_id,
                "quantity": 10,
                "notes": "Réception parcours opérateur",
                "source_screen": "stock.operator_journey",
                "document_type": "operator_journey",
                "document_reference": "OP-JOURNEY-RECEIPT",
            },
        )
        assert receipt_response.status_code == 200, receipt_response.text

        transfer_response = client.post(
            "/v2/stock/transaction",
            headers=headers,
            json={
                "variant_id": variant_id,
                "location_id": rack_id,
                "location_dest_id": rack_b_id,
                "quantity": 4,
                "notes": "Transfert parcours opérateur",
                "source_screen": "stock.operator_journey",
                "document_type": "operator_journey",
                "document_reference": "OP-JOURNEY-TRANSFER",
            },
        )
        assert transfer_response.status_code == 200, transfer_response.text

        quants_response = client.get("/v2/stock/quants", headers=headers)
        assert quants_response.status_code == 200, quants_response.text
        by_location = {
            quant["location_id"]: quant["quantity"]
            for quant in quants_response.json()
            if quant["variant_id"] == variant_id
        }
        assert by_location[rack_id] == 6.0
        assert by_location[rack_b_id] == 4.0

        session_response = client.post(
            "/v2/stock/inventory-sessions",
            headers=headers,
            json={
                "name": "Comptage parcours opérateur",
                "location_id": rack_b_id,
                "notes": "Contrôle zone test",
            },
        )
        assert session_response.status_code == 200, session_response.text
        session_id = session_response.json()["id"]
        assert session_response.json()["zone_locked"] is True

        line_response = client.post(
            f"/v2/stock/inventory-sessions/{session_id}/lines",
            headers=headers,
            json={
                "variant_id": variant_id,
                "location_id": rack_b_id,
                "counted_quantity": 3,
                "reason": "Écart parcours opérateur",
            },
        )
        assert line_response.status_code == 200, line_response.text
        assert line_response.json()["status"] == "variance"
        assert line_response.json()["variance_quantity"] == -1.0

        validate_response = client.post(
            f"/v2/stock/inventory-sessions/{session_id}/validate",
            headers=headers,
        )
        assert validate_response.status_code == 200, validate_response.text
        assert validate_response.json()["status"] == "validated"

        with TestingSessionLocal() as db:
            rack_quant = db.query(models.StockQuant).filter_by(variant_id=variant_id, location_id=rack_id).one()
            rack_b_quant = db.query(models.StockQuant).filter_by(variant_id=variant_id, location_id=rack_b_id).one()
            variant = db.query(models.ProductVariant).filter_by(id=variant_id).one()

        assert rack_quant.quantity == 6.0
        assert rack_b_quant.quantity == 3.0
        assert variant.quantity_in_stock == 9.0

        transactions_response = client.get("/v2/stock/transactions", headers=headers)
        assert transactions_response.status_code == 200, transactions_response.text
        transactions = transactions_response.json()
        assert any(
            transaction["document_reference"] == "OP-JOURNEY-RECEIPT"
            and "Rack A" in transaction["transaction_type"]
            for transaction in transactions
        )
        assert any(
            transaction["document_reference"] == "OP-JOURNEY-TRANSFER"
            and "Rack A" in transaction["transaction_type"]
            and "Rack B" in transaction["transaction_type"]
            for transaction in transactions
        )
        assert any(
            transaction["document_type"] == "inventory_session"
            and transaction["business_reason"] == "Écart parcours opérateur"
            for transaction in transactions
        )
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import database, models
from backend.core import security
from backend.main import app


def test_purchase_order_receipt_creates_stock_move_and_quant():
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

    try:
        client = TestClient(app)
        token = security.create_access_token({"sub": "purchase-tester", "role": "ADMIN"})
        headers = {"Authorization": f"Bearer {token}"}

        product_response = client.post(
            "/v2/stock/products",
            headers=headers,
            json={
                "reference_base": "TEST-PURCHASE-FLOW",
                "name": "Profil test achat",
                "material_type": "PVC",
                "unit": "ml",
                "supplier": "Fournisseur test",
                "variants": [
                    {
                        "reference": "TEST-PURCHASE-FLOW-BLANC",
                        "color": "Blanc",
                        "cost_price": 12.5,
                        "quantity_in_stock": 0,
                        "min_threshold": 5,
                    }
                ],
            },
        )
        assert product_response.status_code == 200, product_response.text
        variant_id = product_response.json()["variants"][0]["id"]

        location_response = client.post(
            "/v2/stock/locations",
            headers=headers,
            json={"name": "WH/Test Achats", "usage": "internal"},
        )
        assert location_response.status_code == 200, location_response.text
        target_location_id = location_response.json()["id"]

        purchase_response = client.post(
            "/v2/purchases/",
            headers=headers,
            json={
                "supplier": "Fournisseur test",
                "notes": "Commande e2e achat stock",
                "lines": [
                    {
                        "variant_id": variant_id,
                        "quantity": 7,
                        "unit_price": 12.5,
                    }
                ],
            },
        )
        assert purchase_response.status_code == 200, purchase_response.text
        po_id = purchase_response.json()["id"]

        receive_response = client.post(
            f"/v2/purchases/{po_id}/receive",
            headers=headers,
            json={"target_location_id": target_location_id},
        )
        assert receive_response.status_code == 200, receive_response.text
        assert receive_response.json() == {"status": "success", "po_status": "RECEIVED"}

        details_response = client.get(f"/v2/purchases/{po_id}", headers=headers)
        assert details_response.status_code == 200, details_response.text
        details = details_response.json()
        assert details["status"] == "RECEIVED"
        assert details["lines"][0]["quantity_received"] == 7

        quants_response = client.get("/v2/stock/quants", headers=headers)
        assert quants_response.status_code == 200, quants_response.text
        quants = quants_response.json()
        assert quants == [
            {
                "id": quants[0]["id"],
                "variant_id": variant_id,
                "location_id": target_location_id,
                "quantity": 7.0,
                "location": {
                    "id": target_location_id,
                    "name": "WH/Test Achats",
                    "usage": "internal",
                    "parent_id": None,
                    "is_active": True,
                },
            }
        ]

        transactions_response = client.get("/v2/stock/transactions", headers=headers)
        assert transactions_response.status_code == 200, transactions_response.text
        transactions = transactions_response.json()
        assert len(transactions) == 1
        assert transactions[0]["reference"] == f"IN/{details['reference']}/{details['lines'][0]['id']}"
        assert transactions[0]["quantity_change"] == 7.0
        assert transactions[0]["transaction_type"] == "Fournisseurs \u2794 WH/Test Achats"
        assert transactions[0]["author"] == "purchase-tester"
        assert transactions[0]["notes"] == f"R\u00e9ception auto depuis {details['reference']}"

        with TestingSessionLocal() as db:
            variant = db.query(models.ProductVariant).filter_by(id=variant_id).one()
            move = db.query(models.StockMove).filter_by(variant_id=variant_id).one()

        assert variant.quantity_in_stock == 0
        assert move.location_dest_id == target_location_id
        assert move.quantity == 7.0
        assert move.state == "done"
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)

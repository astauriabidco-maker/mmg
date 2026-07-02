import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend import database, models
from backend.core import security
from backend.main import app


@pytest.fixture()
def stock_client():
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
        yield TestClient(app), TestingSessionLocal
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def _admin_headers() -> dict[str, str]:
    token = security.create_access_token({"sub": "stock-sales-manager", "role": "ADMIN"})
    return {"Authorization": f"Bearer {token}"}


def _seed_stock_item(db, *, catalog_status: str = "ACTIVE", quantity: float = 5.0):
    product = models.Product(
        reference_base=f"ACC-POIGNEE-{catalog_status}",
        name=f"Poignee baie {catalog_status}",
        material_type="ACCESSOIRE",
        unit="pce",
        supplier="CORTIZO",
        product_type="stockable",
        catalog_status=catalog_status,
    )
    db.add(product)
    db.flush()
    variant = models.ProductVariant(
        product_id=product.id,
        reference=f"ACC-POIGNEE-{catalog_status}-STD",
        supplier_reference=f"POIGNEE-{catalog_status}",
        quantity_in_stock=quantity,
        min_threshold=0,
    )
    stock = models.StockLocation(name="WH/Stock", usage="internal", is_active=True)
    customer = models.StockLocation(name="Partner/Customer", usage="customer", is_active=True)
    db.add_all([variant, stock, customer])
    db.flush()
    db.add(models.StockQuant(variant_id=variant.id, location_id=stock.id, quantity=quantity))
    db.commit()
    return variant.id, stock.id, customer.id


def _create_free_sale_quote(db, variant_id: int, *, quantity: float = 2.0, status: str = "DRAFT"):
    sale = models.SaleOrder(
        reference=f"DEV-LIBRE-STOCK-{variant_id}-{quantity:g}",
        client_name="Client devis libre",
        status=status,
        workflow_type="FREE_SALE",
        tax_rate=20,
    )
    db.add(sale)
    db.flush()
    db.add(
        models.SaleOrderLine(
            order_id=sale.id,
            line_type="STOCK_ITEM",
            variant_id=variant_id,
            description="Poignee baie en stock",
            quantity=quantity,
            unit_price=25,
        )
    )
    db.commit()
    return sale.id


def test_free_sale_rejects_draft_catalog_product(stock_client):
    client, TestingSessionLocal = stock_client
    headers = _admin_headers()

    with TestingSessionLocal() as db:
        variant_id, _stock_id, _customer_id = _seed_stock_item(db, catalog_status="DRAFT", quantity=5)

    response = client.post(
        "/v2/sales/",
        headers=headers,
        json={
            "client_name": "Client devis libre",
            "workflow_type": "FREE_SALE",
            "tax_rate": 20,
            "lines": [
                {
                    "line_type": "STOCK_ITEM",
                    "variant_id": variant_id,
                    "description": "Poignee baie brouillon",
                    "quantity": 1,
                    "unit_price": 25,
                }
            ],
        },
    )

    assert response.status_code == 400
    assert any(token in response.text.lower() for token in ["non actif", "brouillon", "draft"])


def test_free_sale_validation_blocks_when_stock_is_insufficient(stock_client):
    client, TestingSessionLocal = stock_client
    headers = _admin_headers()

    with TestingSessionLocal() as db:
        variant_id, _stock_id, _customer_id = _seed_stock_item(db, quantity=1)
        sale_id = _create_free_sale_quote(db, variant_id, quantity=2)

    response = client.put(f"/v2/sales/{sale_id}/status", params={"status": "VALIDATED"}, headers=headers)

    assert response.status_code == 400
    assert "stock insuffisant" in response.text.lower()

    with TestingSessionLocal() as db:
        assert db.query(models.StockReservation).count() == 0
        assert db.query(models.StockMove).count() == 0


def test_free_sale_validation_reserves_stock_without_physical_debit(stock_client):
    client, TestingSessionLocal = stock_client
    headers = _admin_headers()

    with TestingSessionLocal() as db:
        variant_id, _stock_id, _customer_id = _seed_stock_item(db, quantity=5)
        sale_id = _create_free_sale_quote(db, variant_id, quantity=2)

    response = client.put(f"/v2/sales/{sale_id}/status", params={"status": "VALIDATED"}, headers=headers)

    assert response.status_code == 200, response.text
    with TestingSessionLocal() as db:
        reservation = db.query(models.StockReservation).one()
        line = db.query(models.StockReservationLine).one()
        quant = db.query(models.StockQuant).one()
        variant = db.query(models.ProductVariant).one()

    assert reservation.sale_order_id == sale_id
    assert reservation.production_order_id is None
    assert reservation.status == "reserved"
    assert line.variant_id == variant_id
    assert line.reserved_quantity == 2
    assert quant.quantity == 5
    assert variant.quantity_in_stock == 5


def test_free_sale_full_signature_flow_reserves_stock_without_debit(stock_client):
    client, TestingSessionLocal = stock_client
    headers = _admin_headers()

    with TestingSessionLocal() as db:
        variant_id, _stock_id, _customer_id = _seed_stock_item(db, quantity=5)

    create_response = client.post(
        "/v2/sales/",
        headers=headers,
        json={
            "client_name": "Client devis libre réel",
            "client_contact": "Responsable achat",
            "client_email": "client@example.test",
            "client_address": "1 rue du Stock, 75000 Paris",
            "workflow_type": "FREE_SALE",
            "validity_days": 30,
            "tax_rate": 20,
            "currency": "EUR",
            "lines": [
                {
                    "line_type": "stock",
                    "variant_id": variant_id,
                    "description": "Poignée baie catalogue",
                    "quantity": 2,
                    "unit_price": 25,
                    "discount_pct": 0,
                },
                {
                    "line_type": "service",
                    "variant_id": None,
                    "description": "Prestation SAV",
                    "quantity": 1,
                    "unit_price": 80,
                    "discount_pct": 0,
                },
            ],
        },
    )
    assert create_response.status_code == 200, create_response.text
    sale = create_response.json()
    assert sale["status"] == "DRAFT"
    assert [line["line_type"] for line in sale["lines"]] == ["STOCK_ITEM", "SERVICE"]

    sent_response = client.put(
        f"/v2/sales/{sale['id']}/status",
        params={"status": "SENT"},
        headers=headers,
    )
    assert sent_response.status_code == 200, sent_response.text

    refreshed_response = client.get(f"/v2/sales/{sale['id']}", headers=headers)
    assert refreshed_response.status_code == 200, refreshed_response.text
    signature_token = refreshed_response.json()["signature_token"]
    assert signature_token

    sign_response = client.post(f"/v2/sales/portal/{signature_token}/sign")
    assert sign_response.status_code == 200, sign_response.text
    assert sign_response.json()["commercial_reservation_id"]

    with TestingSessionLocal() as db:
        reservation = db.query(models.StockReservation).one()
        reservation_line = db.query(models.StockReservationLine).one()
        quant = db.query(models.StockQuant).one()
        variant = db.query(models.ProductVariant).one()
        move_count = db.query(models.StockMove).count()
        invoice_count = db.query(models.Invoice).count()

    assert reservation.reference.startswith("RSV-COM")
    assert reservation.sale_order_id == sale["id"]
    assert reservation.production_order_id is None
    assert reservation.source_label == "devis libre"
    assert reservation.status == "reserved"
    assert reservation_line.variant_id == variant_id
    assert reservation_line.requested_quantity == 2
    assert reservation_line.reserved_quantity == 2
    assert quant.quantity == 5
    assert variant.quantity_in_stock == 5
    assert move_count == 0
    assert invoice_count == 1

    products_response = client.get("/v2/stock/products", headers=headers)
    assert products_response.status_code == 200, products_response.text
    [product] = products_response.json()
    [variant_payload] = product["variants"]
    assert variant_payload["quantity_in_stock"] == 5
    assert variant_payload["reserved_quantity"] == 2
    assert variant_payload["available_quantity"] == 3


def test_free_sale_cancellation_releases_commercial_reservation(stock_client):
    client, TestingSessionLocal = stock_client
    headers = _admin_headers()

    with TestingSessionLocal() as db:
        variant_id, _stock_id, _customer_id = _seed_stock_item(db, quantity=5)
        sale_id = _create_free_sale_quote(db, variant_id, quantity=2, status="VALIDATED")
        reservation = models.StockReservation(
            reference="RSV-COMMERCIAL-1",
            sale_order_id=sale_id,
            status="reserved",
            source_label="devis libre",
            created_by="test",
        )
        db.add(reservation)
        db.flush()
        db.add(
            models.StockReservationLine(
                reservation_id=reservation.id,
                variant_id=variant_id,
                supplier_reference="POIGNEE-ACTIVE",
                requested_quantity=2,
                reserved_quantity=2,
                available_at_reservation=5,
                status="reserved",
            )
        )
        db.commit()

    response = client.put(f"/v2/sales/{sale_id}/status", params={"status": "CANCELLED"}, headers=headers)

    assert response.status_code == 200, response.text
    with TestingSessionLocal() as db:
        reservation = db.query(models.StockReservation).one()
        line = db.query(models.StockReservationLine).one()
        moves = db.query(models.StockMove).count()

    assert reservation.status == "cancelled"
    assert line.status == "cancelled"
    assert moves == 0


def test_customer_delivery_move_is_not_classified_as_workshop_debit(stock_client):
    client, TestingSessionLocal = stock_client
    headers = _admin_headers()

    with TestingSessionLocal() as db:
        variant_id, stock_id, customer_id = _seed_stock_item(db, quantity=5)

    response = client.post(
        "/v2/stock/transaction",
        headers=headers,
        json={
            "variant_id": variant_id,
            "location_id": stock_id,
            "location_dest_id": customer_id,
            "quantity": -2,
            "notes": "Livraison client devis libre",
        },
    )
    assert response.status_code == 200, response.text

    transactions_response = client.get("/v2/stock/transactions", headers=headers)
    assert transactions_response.status_code == 200, transactions_response.text
    [move] = transactions_response.json()

    assert move["movement_kind"] == "stock_move"
    assert move["transaction_type"] == "WH/Stock \u2794 Partner/Customer"
    assert not move["reference"].startswith("DEBIT-ATELIER")


def test_free_sale_quote_cannot_be_prepared_or_launched_for_workshop(stock_client):
    client, TestingSessionLocal = stock_client
    headers = _admin_headers()

    with TestingSessionLocal() as db:
        variant_id, _stock_id, _customer_id = _seed_stock_item(db, quantity=5)
        sale_id = _create_free_sale_quote(db, variant_id, quantity=1, status="READY_FOR_PROD")

    launch_response = client.post(f"/v2/sales/{sale_id}/launch-production", headers=headers)

    assert launch_response.status_code == 400
    assert "devis libre" in launch_response.text

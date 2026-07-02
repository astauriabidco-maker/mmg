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


def _seed_service_item(db, *, catalog_status: str = "ACTIVE", price: float = 80.0):
    product = models.Product(
        reference_base=f"SERV-SAV-{catalog_status}",
        name=f"Prestation SAV {catalog_status}",
        material_type="SERVICE",
        unit="forfait",
        supplier="MMG",
        product_type="service",
        available_in_pos=False,
        catalog_status=catalog_status,
    )
    db.add(product)
    db.flush()
    variant = models.ProductVariant(
        product_id=product.id,
        reference=f"SERV-SAV-{catalog_status}-STD",
        supplier_reference=f"SAV-{catalog_status}",
        cost_price=price,
        quantity_in_stock=0,
        min_threshold=0,
    )
    db.add(variant)
    db.commit()
    return variant.id


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


def _sign_and_deliver_free_sale(client: TestClient, sale_id: int, headers: dict[str, str]) -> dict:
    send_response = client.put(f"/v2/sales/{sale_id}/status", params={"status": "SENT"}, headers=headers)
    assert send_response.status_code == 200, send_response.text

    sale_response = client.get(f"/v2/sales/{sale_id}", headers=headers)
    assert sale_response.status_code == 200, sale_response.text
    token = sale_response.json()["signature_token"]

    sign_response = client.post(f"/v2/sales/portal/{token}/sign")
    assert sign_response.status_code == 200, sign_response.text

    deliver_response = client.post(f"/v2/sales/{sale_id}/deliver-free-sale", headers=headers)
    assert deliver_response.status_code == 200, deliver_response.text
    return deliver_response.json()


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


def test_free_sale_rejects_zero_priced_stock_item(stock_client):
    client, TestingSessionLocal = stock_client
    headers = _admin_headers()

    with TestingSessionLocal() as db:
        variant_id, _stock_id, _customer_id = _seed_stock_item(db, quantity=5)

    response = client.post(
        "/v2/sales/",
        headers=headers,
        json={
            "client_name": "Client prix zero",
            "workflow_type": "FREE_SALE",
            "tax_rate": 20,
            "lines": [
                {
                    "line_type": "STOCK_ITEM",
                    "variant_id": variant_id,
                    "description": "Poignee sans prix",
                    "quantity": 1,
                    "unit_price": 0,
                }
            ],
        },
    )

    assert response.status_code == 400
    assert "prix de vente HT positif" in response.text


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
        service_variant_id = _seed_service_item(db, price=80)

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
                    "variant_id": service_variant_id,
                    "description": "Prestation SAV catalogue",
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
    assert sale["lines"][1]["variant_id"] == service_variant_id

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
        variant = db.query(models.ProductVariant).filter(models.ProductVariant.id == variant_id).one()
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
    product = next(product for product in products_response.json() if product["product_type"] == "stockable")
    [variant_payload] = product["variants"]
    assert variant_payload["quantity_in_stock"] == 5
    assert variant_payload["reserved_quantity"] == 2
    assert variant_payload["available_quantity"] == 3
    service_product = next(product for product in products_response.json() if product["product_type"] == "service")
    assert service_product["variants"][0]["quantity_in_stock"] == 0
    assert service_product["variants"][0]["reserved_quantity"] == 0

    detail_response = client.get(f"/v2/sales/{sale['id']}", headers=headers)
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert len(detail["reservations"]) == 1
    assert detail["reservations"][0]["reference"].startswith("RSV-COM")
    assert detail["reservations"][0]["sale_order_id"] == sale["id"]
    assert detail["reservations"][0]["source_label"] == "devis libre"
    assert detail["reservations"][0]["status"] == "reserved"
    assert len(detail["reservations"][0]["lines"]) == 1
    assert detail["reservations"][0]["lines"][0]["variant_id"] == variant_id
    assert detail["reservations"][0]["lines"][0]["reserved_quantity"] == 2
    assert detail["reservations"][0]["lines"][0]["source"].startswith("sale_order_line:")
    assert len(detail["invoices"]) == 1
    assert detail["invoices"][0]["reference"].startswith("F-")
    assert detail["invoices"][0]["total"] == 156


def test_free_sale_delivery_consumes_commercial_reservation(stock_client):
    client, TestingSessionLocal = stock_client
    headers = _admin_headers()

    with TestingSessionLocal() as db:
        variant_id, stock_id, customer_id = _seed_stock_item(db, quantity=5)
        sale_id = _create_free_sale_quote(db, variant_id, quantity=2)

    send_response = client.put(f"/v2/sales/{sale_id}/status", params={"status": "SENT"}, headers=headers)
    assert send_response.status_code == 200, send_response.text

    sale_response = client.get(f"/v2/sales/{sale_id}", headers=headers)
    token = sale_response.json()["signature_token"]
    sign_response = client.post(f"/v2/sales/portal/{token}/sign")
    assert sign_response.status_code == 200, sign_response.text

    deliver_response = client.post(f"/v2/sales/{sale_id}/deliver-free-sale", headers=headers)
    assert deliver_response.status_code == 200, deliver_response.text
    assert deliver_response.json()["created_moves"] == 1
    assert deliver_response.json()["consumed_lines"] == 1
    assert deliver_response.json()["delivery_note_reference"].startswith("BL-")

    with TestingSessionLocal() as db:
        sale = db.query(models.SaleOrder).filter(models.SaleOrder.id == sale_id).one()
        reservation = db.query(models.StockReservation).one()
        reservation_line = db.query(models.StockReservationLine).one()
        source_quant = db.query(models.StockQuant).filter_by(variant_id=variant_id, location_id=stock_id).one()
        customer_quant = db.query(models.StockQuant).filter_by(variant_id=variant_id, location_id=customer_id).one()
        move = db.query(models.StockMove).one()
        delivery_note = db.query(models.DeliveryNote).one()

    assert sale.status == "DELIVERED"
    assert reservation.status == "consumed"
    assert reservation.consumed_at is not None
    assert reservation_line.status == "consumed"
    assert reservation_line.consumed_quantity == 2
    assert source_quant.quantity == 3
    assert customer_quant.quantity == 2
    assert move.reference.startswith("SORTIE-CLIENT")
    assert "Sortie client devis libre" in move.notes
    assert delivery_note.reference == deliver_response.json()["delivery_note_reference"]
    assert delivery_note.sale_order_id == sale_id
    assert delivery_note.order_id is None
    assert delivery_note.status == "DELIVERED"
    assert delivery_note.signed_at is not None
    assert reservation.reference in delivery_note.delivery_notes

    detail_response = client.get(f"/v2/sales/{sale_id}", headers=headers)
    assert detail_response.status_code == 200, detail_response.text
    [delivery_payload] = detail_response.json()["delivery_notes"]
    assert delivery_payload["id"] == delivery_note.id
    assert delivery_payload["reference"] == delivery_note.reference

    pdf_response = client.get(f"/v2/pdf/delivery-note/{delivery_note.id}", headers=headers)
    assert pdf_response.status_code == 200, pdf_response.text
    assert pdf_response.headers["content-type"] == "application/pdf"
    assert pdf_response.content.startswith(b"%PDF")

    products_response = client.get("/v2/stock/products", headers=headers)
    product = next(product for product in products_response.json() if product["product_type"] == "stockable")
    [variant_payload] = product["variants"]
    assert variant_payload["quantity_in_stock"] == 3
    assert variant_payload["reserved_quantity"] == 0
    assert variant_payload["available_quantity"] == 3

    transactions_response = client.get("/v2/stock/transactions", headers=headers)
    [transaction] = transactions_response.json()
    assert transaction["movement_kind"] == "stock_move"
    assert "WH/Stock" in transaction["transaction_type"]
    assert "Partner/Customer" in transaction["transaction_type"]


def test_free_sale_return_recredits_customer_delivery_and_marks_traceability(stock_client):
    client, TestingSessionLocal = stock_client
    headers = _admin_headers()

    with TestingSessionLocal() as db:
        variant_id, stock_id, customer_id = _seed_stock_item(db, quantity=5)
        sale_id = _create_free_sale_quote(db, variant_id, quantity=2)

    delivery_payload = _sign_and_deliver_free_sale(client, sale_id, headers)
    delivery_note_id = delivery_payload["delivery_note_id"]
    delivery_note_reference = delivery_payload["delivery_note_reference"]

    return_response = client.post(f"/v2/sales/{sale_id}/return-free-sale", headers=headers)

    assert return_response.status_code == 200, return_response.text
    return_payload = return_response.json()
    assert return_payload["created_moves"] == 1
    assert return_payload["returned_lines"] == 1
    assert return_payload["delivery_note_id"] == delivery_note_id
    assert return_payload["delivery_note_reference"] == delivery_note_reference

    with TestingSessionLocal() as db:
        sale = db.query(models.SaleOrder).filter(models.SaleOrder.id == sale_id).one()
        reservation = db.query(models.StockReservation).one()
        reservation_line = db.query(models.StockReservationLine).one()
        source_quant = db.query(models.StockQuant).filter_by(variant_id=variant_id, location_id=stock_id).one()
        customer_quant = db.query(models.StockQuant).filter_by(variant_id=variant_id, location_id=customer_id).one()
        variant = db.query(models.ProductVariant).filter(models.ProductVariant.id == variant_id).one()
        moves = db.query(models.StockMove).order_by(models.StockMove.id.asc()).all()
        delivery_note = db.query(models.DeliveryNote).filter(models.DeliveryNote.id == delivery_note_id).one()

    assert sale.status == "VALIDATED"
    assert reservation.status == "returned"
    assert reservation_line.status == "returned"
    assert reservation_line.consumed_quantity == 2
    assert source_quant.quantity == 5
    assert customer_quant.quantity == 0
    assert variant.quantity_in_stock == 5
    assert len(moves) == 2
    delivery_move, return_move = moves
    assert delivery_move.reference.startswith("SORTIE-CLIENT")
    assert return_move.reference.startswith("RETOUR-CLIENT")
    assert return_move.location_id == customer_id
    assert return_move.location_dest_id == stock_id
    assert return_move.quantity == 2
    assert "Retour client devis libre" in return_move.notes
    assert reservation.reference in return_move.notes
    assert delivery_note.status in {"RETURNED", "CANCELLED"}
    assert "Retour client" in delivery_note.delivery_notes

    detail_response = client.get(f"/v2/sales/{sale_id}", headers=headers)
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    [reservation_payload] = detail["reservations"]
    [reservation_line_payload] = reservation_payload["lines"]
    [delivery_note_payload] = detail["delivery_notes"]
    assert reservation_payload["status"] == "returned"
    assert reservation_line_payload["status"] == "returned"
    assert reservation_line_payload["consumed_quantity"] == 2
    assert delivery_note_payload["id"] == delivery_note_id
    assert delivery_note_payload["reference"] == delivery_note_reference
    assert delivery_note_payload["status"] in {"RETURNED", "CANCELLED"}
    assert "Retour client" in delivery_note_payload["delivery_notes"]

    products_response = client.get("/v2/stock/products", headers=headers)
    assert products_response.status_code == 200, products_response.text
    product = next(product for product in products_response.json() if product["product_type"] == "stockable")
    [variant_payload] = product["variants"]
    assert variant_payload["quantity_in_stock"] == 5
    assert variant_payload["reserved_quantity"] == 0
    assert variant_payload["available_quantity"] == 5

    transactions_response = client.get("/v2/stock/transactions", headers=headers)
    assert transactions_response.status_code == 200, transactions_response.text
    transactions = transactions_response.json()
    assert [transaction["movement_kind"] for transaction in transactions] == ["stock_move", "stock_move"]
    assert any("Partner/Customer" in transaction["transaction_type"] for transaction in transactions)
    assert any("WH/Stock" in transaction["transaction_type"] for transaction in transactions)


def test_free_sale_return_does_not_create_credit_note_automatically(stock_client):
    client, TestingSessionLocal = stock_client
    headers = _admin_headers()

    with TestingSessionLocal() as db:
        variant_id, _stock_id, _customer_id = _seed_stock_item(db, quantity=5)
        sale_id = _create_free_sale_quote(db, variant_id, quantity=2)

    _sign_and_deliver_free_sale(client, sale_id, headers)

    with TestingSessionLocal() as db:
        [source_invoice] = db.query(models.Invoice).filter(models.Invoice.sale_order_id == sale_id).all()
        assert source_invoice.status == "UNPAID"
        assert source_invoice.reference.startswith("F-")

    return_response = client.post(f"/v2/sales/{sale_id}/return-free-sale", headers=headers)

    assert return_response.status_code == 200, return_response.text

    with TestingSessionLocal() as db:
        invoices = db.query(models.Invoice).filter(models.Invoice.sale_order_id == sale_id).order_by(models.Invoice.id).all()

    assert len(invoices) == 1
    assert invoices[0].reference.startswith("F-")
    assert invoices[0].status == "UNPAID"
    assert invoices[0].total == 60


def test_free_sale_return_credit_note_requires_explicit_post_and_is_idempotent(stock_client):
    client, TestingSessionLocal = stock_client
    headers = _admin_headers()

    with TestingSessionLocal() as db:
        variant_id, _stock_id, _customer_id = _seed_stock_item(db, quantity=5)
        sale_id = _create_free_sale_quote(db, variant_id, quantity=2)

    delivery_payload = _sign_and_deliver_free_sale(client, sale_id, headers)
    return_response = client.post(f"/v2/sales/{sale_id}/return-free-sale", headers=headers)
    assert return_response.status_code == 200, return_response.text

    with TestingSessionLocal() as db:
        source_invoice = db.query(models.Invoice).filter(models.Invoice.sale_order_id == sale_id).one()
        return_move = (
            db.query(models.StockMove)
            .filter(models.StockMove.reference.like("RETOUR-CLIENT%"))
            .one()
        )
        delivery_note = db.query(models.DeliveryNote).filter(models.DeliveryNote.id == delivery_payload["delivery_note_id"]).one()
        source_invoice_id = source_invoice.id
        source_invoice_reference = source_invoice.reference
        return_move_id = return_move.id
        delivery_note_id = delivery_note.id

    credit_response = client.post(
        f"/v2/accounting/invoices/{source_invoice_id}/credit-note-from-return",
        headers=headers,
    )

    assert credit_response.status_code == 200, credit_response.text
    credit_note = credit_response.json()
    assert credit_note["id"] != source_invoice_id
    assert credit_note["reference"].startswith("AV-")
    assert credit_note["status"] == "AVOIR"
    assert credit_note["source_invoice_id"] == source_invoice_id
    assert credit_note["source_invoice_reference"] == source_invoice_reference
    assert credit_note["sale_order_id"] == sale_id
    assert credit_note["return_move_id"] == return_move_id
    assert credit_note["delivery_note_id"] == delivery_note_id
    assert credit_note["subtotal"] == -50
    assert credit_note["tax_amount"] == -10
    assert credit_note["total"] == -60
    assert [line["description"] for line in credit_note["lines"]] == ["Avoir sur: Poignee baie en stock"]

    with TestingSessionLocal() as db:
        source_invoice = db.query(models.Invoice).filter(models.Invoice.id == source_invoice_id).one()
        invoices = db.query(models.Invoice).filter(models.Invoice.sale_order_id == sale_id).order_by(models.Invoice.id).all()
        credit_notes = [invoice for invoice in invoices if invoice.status == "AVOIR"]

    assert source_invoice.status == "UNPAID"
    assert len(invoices) == 2
    assert len(credit_notes) == 1
    assert credit_notes[0].reference == credit_note["reference"]
    assert credit_notes[0].total == -60

    duplicate_response = client.post(
        f"/v2/accounting/invoices/{source_invoice_id}/credit-note-from-return",
        headers=headers,
    )

    assert duplicate_response.status_code in {400, 409}
    assert any(token in duplicate_response.text.lower() for token in ["avoir", "déjà", "deja", "retour"])

    with TestingSessionLocal() as db:
        invoices_after_duplicate = db.query(models.Invoice).filter(models.Invoice.sale_order_id == sale_id).all()

    assert len([invoice for invoice in invoices_after_duplicate if invoice.status == "AVOIR"]) == 1

    pdf_response = client.get(f"/v2/pdf/invoice/{credit_note['id']}", headers=headers)
    assert pdf_response.status_code == 200, pdf_response.text
    assert pdf_response.headers["content-type"] == "application/pdf"
    assert pdf_response.content.startswith(b"%PDF")


def test_free_sale_return_cannot_be_applied_twice(stock_client):
    client, TestingSessionLocal = stock_client
    headers = _admin_headers()

    with TestingSessionLocal() as db:
        variant_id, stock_id, customer_id = _seed_stock_item(db, quantity=5)
        sale_id = _create_free_sale_quote(db, variant_id, quantity=2)

    _sign_and_deliver_free_sale(client, sale_id, headers)

    first_return_response = client.post(f"/v2/sales/{sale_id}/return-free-sale", headers=headers)
    assert first_return_response.status_code == 200, first_return_response.text

    second_return_response = client.post(f"/v2/sales/{sale_id}/return-free-sale", headers=headers)

    assert second_return_response.status_code == 400
    assert any(token in second_return_response.text.lower() for token in ["déjà retourn", "deja retourn", "retour"])

    with TestingSessionLocal() as db:
        reservation = db.query(models.StockReservation).one()
        reservation_line = db.query(models.StockReservationLine).one()
        source_quant = db.query(models.StockQuant).filter_by(variant_id=variant_id, location_id=stock_id).one()
        customer_quant = db.query(models.StockQuant).filter_by(variant_id=variant_id, location_id=customer_id).one()
        moves = db.query(models.StockMove).order_by(models.StockMove.id.asc()).all()
        return_moves = [move for move in moves if move.reference.startswith("RETOUR-CLIENT")]
        delivery_note = db.query(models.DeliveryNote).one()

    assert reservation.status == "returned"
    assert reservation_line.status == "returned"
    assert source_quant.quantity == 5
    assert customer_quant.quantity == 0
    assert len(moves) == 2
    assert len(return_moves) == 1
    assert delivery_note.status in {"RETURNED", "CANCELLED"}


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

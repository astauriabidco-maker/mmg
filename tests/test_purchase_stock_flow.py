from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import database, models
from backend.core import security
from backend.core.time import utcnow
from backend.main import app


def _auth_headers(session_factory, username: str, role: str = "ADMIN") -> dict:
    """Crée l'utilisateur en base si besoin, puis émet un JWT valide pour lui."""
    with session_factory() as db:
        if not db.query(models.User).filter(models.User.username == username).first():
            db.add(models.User(username=username, pin_hash="test-pin", role=role, is_active=True))
            db.commit()
    token = security.create_access_token({"sub": username, "role": role})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def purchase_test_client():
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


def _seed_purchase_need_variant(
    db,
    *,
    reference: str,
    supplier: str = "Fournisseur test",
    catalog_status: str = "ACTIVE",
    supplier_status: str = "ACTIVE",
    physical_quantity: float = 0,
    min_threshold: float = 5,
):
    supplier_record = db.query(models.Supplier).filter_by(name=supplier).first()
    if not supplier_record:
        supplier_record = models.Supplier(name=supplier, supplier_status=supplier_status)
        db.add(supplier_record)
    else:
        supplier_record.supplier_status = supplier_status

    product = models.Product(
        reference_base=reference,
        name=f"Article besoin {reference}",
        material_type="ACCESSOIRE",
        unit="pce",
        supplier=supplier,
        product_type="stockable",
        catalog_status=catalog_status,
    )
    db.add(product)
    db.flush()
    variant = models.ProductVariant(
        product_id=product.id,
        reference=reference,
        supplier_reference=reference,
        quantity_in_stock=physical_quantity,
        min_threshold=min_threshold,
    )
    location = models.StockLocation(name=f"WH/{reference}", usage="internal", is_active=True)
    db.add_all([variant, location])
    db.flush()
    db.add(models.StockQuant(variant_id=variant.id, location_id=location.id, quantity=physical_quantity))
    db.commit()
    return variant.id


def _grant_role_permissions(db, role_name: str, permission_codes: list[str]) -> None:
    role = db.query(models.Role).filter_by(name=role_name).first()
    if not role:
        role = models.Role(name=role_name, description=f"Test role {role_name}")
        db.add(role)
        db.flush()
    for code in permission_codes:
        permission = db.query(models.Permission).filter_by(code=code).first()
        if not permission:
            permission = models.Permission(code=code, module="Tests", description=code)
            db.add(permission)
            db.flush()
        if permission not in role.permissions:
            role.permissions.append(permission)
    db.commit()


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
        headers = _auth_headers(TestingSessionLocal, "purchase-tester")

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
            json={"name": "Rack Achats", "usage": "internal"},
        )
        assert location_response.status_code == 200, location_response.text
        target_location_id = location_response.json()["id"]

        purchase_response = client.post(
            "/v2/purchases/",
            headers=headers,
            json={
                "supplier": "Fournisseur test",
                "notes": "Commande e2e achat stock",
                "global_discount_percent": 5,
                "lines": [
                    {
                        "variant_id": variant_id,
                        "quantity": 7,
                        "unit_price": 12.5,
                        "discount_percent": 10,
                    }
                ],
            },
        )
        assert purchase_response.status_code == 200, purchase_response.text
        po_id = purchase_response.json()["id"]

        vague_location_response = client.post(
            "/v2/stock/locations",
            headers=headers,
            json={"name": "Stock vague achats", "usage": "internal"},
        )
        assert vague_location_response.status_code == 200, vague_location_response.text
        blocked_receive_response = client.post(
            f"/v2/purchases/{po_id}/receive",
            headers=headers,
            json={"target_location_id": vague_location_response.json()["id"]},
        )
        assert blocked_receive_response.status_code == 400
        assert "Emplacement non exploitable" in blocked_receive_response.json()["detail"]

        receive_response = client.post(
            f"/v2/purchases/{po_id}/receive",
            headers=headers,
            json={"target_location_id": target_location_id},
        )
        assert receive_response.status_code == 200, receive_response.text
        assert receive_response.json() == {
            "status": "success",
            "po_status": "RECEIVED",
            "received_lines": 1,
            "received_quantity": 7.0,
        }

        details_response = client.get(f"/v2/purchases/{po_id}", headers=headers)
        assert details_response.status_code == 200, details_response.text
        details = details_response.json()
        assert details["status"] == "RECEIVED"
        assert details["operational_status"] == "INVOICE_TO_MATCH"
        assert details["receipt_status"] == "FULL"
        assert details["invoice_match_status"] == "TO_MATCH"
        assert details["next_action"] == "Rapprocher facture fournisseur"
        assert details["quantity_ordered"] == 7.0
        assert details["quantity_remaining"] == 0.0
        assert details["quantity_invoiceable"] == 7.0
        assert details["global_discount_percent"] == 5
        assert details["total_amount"] == 74.81  # 78.75 x 0.95, arrondi centime (Numeric(14,2))
        assert details["lines"][0]["discount_percent"] == 10
        assert details["lines"][0]["line_total"] == 78.75
        assert details["lines"][0]["quantity_received"] == 7
        assert details["lines"][0]["quantity_remaining"] == 0
        assert details["lines"][0]["receipt_status"] == "RECEIVED"
        assert details["lines"][0]["invoice_match_status"] == "TO_INVOICE"

        quants_response = client.get("/v2/stock/quants", headers=headers)
        assert quants_response.status_code == 200, quants_response.text
        quants = quants_response.json()
        assert quants == [
            {
                "id": quants[0]["id"],
                "variant_id": variant_id,
                "location_id": target_location_id,
                "quantity": 7.0,
                # Emplacement interne sans réservation : exposés par M4.
                "reserved_quantity": 0.0,
                "available_quantity": 7.0,
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
        assert transactions[0]["notes"] == f"R\u00e9ception fournisseur depuis {details['reference']}"
        assert transactions[0]["source_screen"] == "purchases.receipt"
        assert transactions[0]["document_type"] == "purchase_order"
        assert transactions[0]["document_reference"] == details["reference"]
        assert transactions[0]["business_reason"] == "Réception fournisseur"

        with TestingSessionLocal() as db:
            variant = db.query(models.ProductVariant).filter_by(id=variant_id).one()
            move = db.query(models.StockMove).filter_by(variant_id=variant_id).one()

        assert variant.quantity_in_stock == 7.0
        assert move.location_dest_id == target_location_id
        assert move.quantity == 7.0
        assert move.state == "done"
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def test_purchase_order_can_be_received_partially_then_completed():
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
        headers = _auth_headers(TestingSessionLocal, "purchase-tester")

        product_response = client.post(
            "/v2/stock/products",
            headers=headers,
            json={
                "reference_base": "TEST-PARTIAL-PO",
                "name": "Profil réception partielle",
                "material_type": "PVC",
                "unit": "barre",
                "supplier": "Fournisseur test",
                "variants": [
                    {
                        "reference": "TEST-PARTIAL-PO-001",
                        "quantity_in_stock": 0,
                    }
                ],
            },
        )
        assert product_response.status_code == 200, product_response.text
        variant_id = product_response.json()["variants"][0]["id"]

        location_response = client.post(
            "/v2/stock/locations",
            headers=headers,
            json={"name": "Rack Réception partielle", "usage": "internal"},
        )
        assert location_response.status_code == 200, location_response.text
        target_location_id = location_response.json()["id"]

        purchase_response = client.post(
            "/v2/purchases/",
            headers=headers,
            json={
                "supplier": "Fournisseur test",
                "lines": [{"variant_id": variant_id, "quantity": 7, "unit_price": 10}],
            },
        )
        assert purchase_response.status_code == 200, purchase_response.text
        po_id = purchase_response.json()["id"]

        details_response = client.get(f"/v2/purchases/{po_id}", headers=headers)
        line_id = details_response.json()["lines"][0]["id"]

        partial_response = client.post(
            f"/v2/purchases/{po_id}/receive",
            headers=headers,
            json={
                "target_location_id": target_location_id,
                "lines": [{"line_id": line_id, "quantity": 3}],
            },
        )
        assert partial_response.status_code == 200, partial_response.text
        assert partial_response.json()["po_status"] == "PARTIAL"
        assert partial_response.json()["received_quantity"] == 3.0

        details_response = client.get(f"/v2/purchases/{po_id}", headers=headers)
        details = details_response.json()
        assert details["status"] == "PARTIAL"
        assert details["operational_status"] == "PARTIAL_RECEIPT"
        assert details["receipt_status"] == "PARTIAL"
        assert details["invoice_match_status"] == "TO_MATCH"
        assert details["next_action"] == "Réceptionner fournisseur"
        assert details["quantity_ordered"] == 7.0
        assert details["quantity_remaining"] == 4.0
        assert details["quantity_invoiceable"] == 3.0
        assert details["lines"][0]["quantity_received"] == 3.0
        assert details["lines"][0]["quantity_remaining"] == 4.0
        assert details["lines"][0]["quantity_invoiceable"] == 3.0
        assert details["lines"][0]["receipt_status"] == "PARTIAL"
        assert details["lines"][0]["invoice_match_status"] == "TO_INVOICE"

        over_invoice_response = client.post(
            f"/v2/purchases/{po_id}/supplier-invoices",
            headers=headers,
            json={
                "supplier_reference": "FAC-OVER",
                "lines": [{"purchase_order_line_id": line_id, "quantity": 4}],
            },
        )
        assert over_invoice_response.status_code == 400, over_invoice_response.text
        assert "supérieure au reçu non facturé" in over_invoice_response.json()["detail"]

        negative_price_invoice_response = client.post(
            f"/v2/purchases/{po_id}/supplier-invoices",
            headers=headers,
            json={
                "supplier_reference": "FAC-NEGATIVE",
                "lines": [{"purchase_order_line_id": line_id, "quantity": 1, "unit_price": -1}],
            },
        )
        assert negative_price_invoice_response.status_code == 400, negative_price_invoice_response.text
        assert "Prix facturé négatif interdit" in negative_price_invoice_response.json()["detail"]

        invoice_response = client.post(
            f"/v2/purchases/{po_id}/supplier-invoices",
            headers=headers,
            json={
                "supplier_reference": "FAC-PARTIAL",
                "lines": [{"purchase_order_line_id": line_id, "quantity": 2, "unit_price": 11}],
            },
        )
        assert invoice_response.status_code == 200, invoice_response.text
        supplier_invoice = invoice_response.json()
        assert supplier_invoice["reference"].startswith("FF-")
        assert supplier_invoice["supplier_reference"] == "FAC-PARTIAL"
        assert supplier_invoice["total_amount"] == 22.0
        assert supplier_invoice["lines"][0]["unit_price"] == 11.0
        assert supplier_invoice["paid_amount"] == 0.0
        assert supplier_invoice["remaining_amount"] == 22.0

        payment_response = client.post(
            f"/v2/purchases/supplier-invoices/{supplier_invoice['id']}/pay",
            headers=headers,
            json={"amount": 5, "method": "TRANSFER", "reference": "VIR-001"},
        )
        assert payment_response.status_code == 200, payment_response.text
        paid_invoice = payment_response.json()
        assert paid_invoice["status"] == "PARTIAL"
        assert paid_invoice["paid_amount"] == 5.0
        assert paid_invoice["remaining_amount"] == 17.0

        details_response = client.get(f"/v2/purchases/{po_id}", headers=headers)
        details = details_response.json()
        assert details["supplier_invoice_status"] == "PARTIAL"
        assert details["invoice_match_status"] == "PARTIAL_MATCH"
        assert details["operational_status"] == "PARTIAL_RECEIPT"
        assert details["quantity_invoiced"] == 2.0
        assert details["quantity_invoiceable"] == 1.0
        assert details["lines"][0]["quantity_invoiced"] == 2.0
        assert details["lines"][0]["quantity_invoiceable"] == 1.0
        assert details["lines"][0]["invoice_match_status"] == "PARTIAL_MATCH"
        assert len(details["supplier_invoices"]) == 1
        assert details["supplier_invoices"][0]["paid_amount"] == 5.0

        over_receive_response = client.post(
            f"/v2/purchases/{po_id}/receive",
            headers=headers,
            json={
                "target_location_id": target_location_id,
                "lines": [{"line_id": line_id, "quantity": 5}],
            },
        )
        assert over_receive_response.status_code == 400, over_receive_response.text
        assert "supérieure au reste" in over_receive_response.json()["detail"]

        complete_response = client.post(
            f"/v2/purchases/{po_id}/receive",
            headers=headers,
            json={
                "target_location_id": target_location_id,
                "lines": [{"line_id": line_id, "quantity": 4}],
            },
        )
        assert complete_response.status_code == 200, complete_response.text
        assert complete_response.json()["po_status"] == "RECEIVED"

        final_invoice_response = client.post(
            f"/v2/purchases/{po_id}/supplier-invoices",
            headers=headers,
            json={
                "supplier_reference": "FAC-BALANCE",
                "lines": [{"purchase_order_line_id": line_id, "quantity": 5}],
            },
        )
        assert final_invoice_response.status_code == 200, final_invoice_response.text
        final_invoice = final_invoice_response.json()

        dispute_response = client.post(
            "/v2/purchases/disputes",
            headers=headers,
            json={
                "supplier": "Fournisseur test",
                "purchase_order_id": po_id,
                "supplier_invoice_id": final_invoice["id"],
                "title": "Prix facture à vérifier",
                "category": "PRICE",
                "severity": "BLOCKING",
                "expected_action": "PRICE_CORRECTION",
                "blocks_payment": True,
            },
        )
        assert dispute_response.status_code == 200, dispute_response.text

        blocked_payment = client.post(
            f"/v2/purchases/supplier-invoices/{final_invoice['id']}/pay",
            headers=headers,
            json={"amount": 10, "method": "TRANSFER"},
        )
        assert blocked_payment.status_code == 409, blocked_payment.text
        assert "Paiement fournisseur bloqué" in blocked_payment.json()["detail"]

        resolve_response = client.post(
            f"/v2/purchases/disputes/{dispute_response.json()['id']}/resolve",
            headers=headers,
            json={"resolution_notes": "Prix confirmé par le fournisseur."},
        )
        assert resolve_response.status_code == 200, resolve_response.text

        final_payment_response = client.post(
            f"/v2/purchases/supplier-invoices/{final_invoice['id']}/pay",
            headers=headers,
            json={"amount": final_invoice["remaining_amount"], "method": "TRANSFER", "reference": "VIR-002"},
        )
        assert final_payment_response.status_code == 200, final_payment_response.text
        assert final_payment_response.json()["status"] == "PAID"

        details_response = client.get(f"/v2/purchases/{po_id}", headers=headers)
        details = details_response.json()
        assert details["operational_status"] == "READY_TO_CLOSE"
        assert details["receipt_status"] == "FULL"
        assert details["invoice_match_status"] == "MATCHED"
        assert details["next_action"] == "Clôturer après contrôle"
        assert details["supplier_invoice_status"] == "FULL"
        assert details["quantity_received"] == 7.0
        assert details["quantity_remaining"] == 0.0
        assert details["quantity_invoiced"] == 7.0
        assert details["lines"][0]["quantity_invoiceable"] == 0.0
        assert details["lines"][0]["invoice_match_status"] == "MATCHED"

        with TestingSessionLocal() as db:
            quant = db.query(models.StockQuant).filter_by(variant_id=variant_id, location_id=target_location_id).one()
            moves = db.query(models.StockMove).filter_by(variant_id=variant_id).all()
            supplier_invoices = db.query(models.SupplierInvoice).filter_by(purchase_order_id=po_id).all()

        assert quant.quantity == 7.0
        assert sorted(move.quantity for move in moves) == [3.0, 4.0]
        assert len(supplier_invoices) == 2
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def test_supplier_operational_purchase_list_flags_open_receipt_invoice_and_overbilling():
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
        headers = _auth_headers(TestingSessionLocal, "supplier-ops-tester")

        product_response = client.post(
            "/v2/stock/products",
            headers=headers,
            json={
                "reference_base": "TEST-SUPPLIER-OPS",
                "name": "Joint fournisseur pilotage",
                "material_type": "ACCESSOIRE",
                "unit": "pce",
                "supplier": "Ops Supplier",
                "variants": [
                    {
                        "reference": "TEST-SUPPLIER-OPS-001",
                        "quantity_in_stock": 0,
                    }
                ],
            },
        )
        assert product_response.status_code == 200, product_response.text
        variant_id = product_response.json()["variants"][0]["id"]

        location_response = client.post(
            "/v2/stock/locations",
            headers=headers,
            json={"name": "Rack Fiche Fournisseur", "usage": "internal"},
        )
        assert location_response.status_code == 200, location_response.text
        target_location_id = location_response.json()["id"]

        expected_date = (utcnow() - timedelta(days=2)).isoformat()
        purchase_response = client.post(
            "/v2/purchases/",
            headers=headers,
            json={
                "supplier": "Ops Supplier",
                "expected_date": expected_date,
                "lines": [{"variant_id": variant_id, "quantity": 10, "unit_price": 4}],
            },
        )
        assert purchase_response.status_code == 200, purchase_response.text
        po_id = purchase_response.json()["id"]

        line_id = client.get(f"/v2/purchases/{po_id}", headers=headers).json()["lines"][0]["id"]
        partial_receipt = client.post(
            f"/v2/purchases/{po_id}/receive",
            headers=headers,
            json={
                "target_location_id": target_location_id,
                "lines": [{"line_id": line_id, "quantity": 3}],
            },
        )
        assert partial_receipt.status_code == 200, partial_receipt.text

        too_high_invoice = client.post(
            f"/v2/purchases/{po_id}/supplier-invoices",
            headers=headers,
            json={
                "supplier_reference": "FAC-TROP-HAUTE",
                "lines": [{"purchase_order_line_id": line_id, "quantity": 4}],
            },
        )
        assert too_high_invoice.status_code == 400, too_high_invoice.text
        assert "supérieure au reçu non facturé" in too_high_invoice.json()["detail"]

        purchase_list_response = client.get("/v2/purchases/", headers=headers)
        assert purchase_list_response.status_code == 200, purchase_list_response.text
        [supplier_po] = [
            po for po in purchase_list_response.json()
            if po["supplier"] == "Ops Supplier" and po["id"] == po_id
        ]

        assert supplier_po["status"] == "PARTIAL"
        assert supplier_po["operational_status"] == "LATE_RECEIPT"
        assert supplier_po["receipt_status"] == "PARTIAL"
        assert supplier_po["invoice_match_status"] == "TO_MATCH"
        assert supplier_po["supplier_invoice_status"] == "NONE"
        assert supplier_po["next_action"] == "Relancer fournisseur"
        assert supplier_po["is_late"] is True
        assert supplier_po["late_days"] >= 2
        assert supplier_po["quantity_ordered"] == 10.0
        assert supplier_po["quantity_received"] == 3.0
        assert supplier_po["quantity_remaining"] == 7.0
        assert supplier_po["quantity_invoiceable"] == 3.0
        assert supplier_po["expected_date"] is not None
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def test_supplier_operational_purchase_list_exposes_late_purchase_orders():
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
        headers = _auth_headers(TestingSessionLocal, "supplier-late-tester")

        product_response = client.post(
            "/v2/stock/products",
            headers=headers,
            json={
                "reference_base": "TEST-SUPPLIER-LATE",
                "name": "Article fournisseur retard",
                "material_type": "ACCESSOIRE",
                "unit": "pce",
                "supplier": "Late Supplier",
                "variants": [{"reference": "TEST-SUPPLIER-LATE-001", "quantity_in_stock": 0}],
            },
        )
        assert product_response.status_code == 200, product_response.text

        purchase_response = client.post(
            "/v2/purchases/",
            headers=headers,
            json={
                "supplier": "Late Supplier",
                "expected_date": (utcnow() - timedelta(days=3)).isoformat(),
                "lines": [
                    {
                        "variant_id": product_response.json()["variants"][0]["id"],
                        "quantity": 5,
                        "unit_price": 2,
                    }
                ],
            },
        )
        assert purchase_response.status_code == 200, purchase_response.text

        purchase_list = client.get("/v2/purchases/", headers=headers).json()
        [late_po] = [po for po in purchase_list if po["supplier"] == "Late Supplier"]
        assert late_po["is_late"] is True
        assert late_po["late_days"] >= 3
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def test_purchase_dashboard_pdf_and_supplier_reminder(purchase_test_client, monkeypatch):
    client, TestingSessionLocal = purchase_test_client
    headers = _auth_headers(TestingSessionLocal, "purchase-dashboard-tester")
    sent_email = {}

    def fake_send_smtp_email(recipient, subject, text_body, html_body, attachments=None, cc=None):
        sent_email["recipient"] = recipient
        sent_email["subject"] = subject
        sent_email["attachments"] = attachments or []
        return True

    monkeypatch.setattr("backend.routers.v2_purchases._send_smtp_email", fake_send_smtp_email)
    with TestingSessionLocal() as db:
        variant_id = _seed_purchase_need_variant(
            db,
            reference="ACH-DASH-001",
            supplier="Dashboard Supplier",
            physical_quantity=0,
            min_threshold=0,
        )

    purchase_response = client.post(
        "/v2/purchases/",
        headers=headers,
        json={
            "supplier": "Dashboard Supplier",
            "expected_date": (utcnow() - timedelta(days=3)).isoformat(),
            "lines": [{"variant_id": variant_id, "quantity": 4, "unit_price": 12}],
        },
    )
    assert purchase_response.status_code == 200, purchase_response.text
    po_id = purchase_response.json()["id"]

    dashboard_response = client.get("/v2/purchases/dashboard", headers=headers)
    assert dashboard_response.status_code == 200, dashboard_response.text
    dashboard = dashboard_response.json()
    assert dashboard["summary"]["to_receive"] >= 1
    assert dashboard["summary"]["late_orders"] >= 1
    assert any(action["purchase_order_id"] == po_id and action["type"] == "LATE" for action in dashboard["actions"])

    pdf_response = client.get(f"/v2/purchases/{po_id}/pdf", headers=headers)
    assert pdf_response.status_code == 200, pdf_response.text
    assert pdf_response.headers["content-type"].startswith("application/pdf")
    assert pdf_response.content.startswith(b"%PDF")

    reminder_response = client.post(
        f"/v2/purchases/{po_id}/remind",
        headers=headers,
        json={
            "channel": "email",
            "recipient": "achats@dashboard-supplier.test",
            "message": "Merci de confirmer la date de livraison.",
        },
    )
    assert reminder_response.status_code == 200, reminder_response.text
    assert reminder_response.json()["status"] == "SENT"
    assert reminder_response.json()["reminder"]["recipient"] == "achats@dashboard-supplier.test"
    assert sent_email["recipient"] == "achats@dashboard-supplier.test"
    assert sent_email["attachments"][0]["filename"].endswith(".pdf")
    assert sent_email["attachments"][0]["content"].startswith(b"%PDF")

    details = client.get(f"/v2/purchases/{po_id}", headers=headers).json()
    assert "[RELANCE FOURNISSEUR]" in details["notes"]
    assert details["supplier_reminders"][0]["message"] == "Merci de confirmer la date de livraison."

    with TestingSessionLocal() as db:
        stock_location = db.query(models.StockLocation).filter(models.StockLocation.name == "WH/ACH-DASH-001").first()
        assert stock_location is not None
        stock_location_id = stock_location.id

    details = client.get(f"/v2/purchases/{po_id}", headers=headers).json()
    receive_response = client.post(
        f"/v2/purchases/{po_id}/receive",
        headers=headers,
        json={
            "target_location_id": stock_location_id,
            "lines": [{"line_id": details["lines"][0]["id"], "quantity": 4}],
        },
    )
    assert receive_response.status_code == 200, receive_response.text

    invoice_response = client.post(
        f"/v2/purchases/{po_id}/supplier-invoices",
        headers=headers,
        json={
            "supplier_reference": "FAC-DASH-001",
            "due_date": (utcnow() - timedelta(days=1)).isoformat(),
            "lines": [{"purchase_order_line_id": details["lines"][0]["id"], "quantity": 4}],
        },
    )
    assert invoice_response.status_code == 200, invoice_response.text
    supplier_invoice = invoice_response.json()

    payment_dashboard_response = client.get("/v2/purchases/dashboard", headers=headers)
    assert payment_dashboard_response.status_code == 200, payment_dashboard_response.text
    payment_dashboard = payment_dashboard_response.json()
    assert payment_dashboard["summary"]["supplier_invoices_to_pay"] >= 1
    assert payment_dashboard["summary"]["supplier_invoices_overdue"] >= 1
    assert payment_dashboard["summary"]["amount_to_pay"] >= 48.0
    assert payment_dashboard["summary"]["cash_out_7_days"] >= 48.0
    assert any(item["invoice_id"] == supplier_invoice["id"] and item["is_overdue"] for item in payment_dashboard["payment_schedule"])

    dispute_response = client.post(
        "/v2/purchases/disputes",
        headers=headers,
        json={
            "supplier": "Dashboard Supplier",
            "purchase_order_id": po_id,
            "supplier_invoice_id": supplier_invoice["id"],
            "title": "Blocage paiement test",
            "category": "PRICE",
            "severity": "HIGH",
            "expected_action": "PRICE_CORRECTION",
            "blocks_payment": True,
        },
    )
    assert dispute_response.status_code == 200, dispute_response.text

    blocked_dashboard = client.get("/v2/purchases/dashboard", headers=headers).json()
    assert blocked_dashboard["summary"]["supplier_invoices_blocked"] >= 1
    assert any(
        item["invoice_id"] == supplier_invoice["id"] and item["is_blocked"]
        for item in blocked_dashboard["payment_schedule"]
    )
    assert any(
        action["type"] == "PAYMENT_BLOCKED" and action["purchase_order_id"] == po_id
        for action in blocked_dashboard["actions"]
    )


def test_purchase_recommendations_use_real_stock_thresholds_without_fake_fallback():
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
        headers = _auth_headers(TestingSessionLocal, "purchase-tester")

        empty_response = client.get("/v2/purchases/ai-recommendations", headers=headers)
        assert empty_response.status_code == 200, empty_response.text
        assert empty_response.json() == []

        product_response = client.post(
            "/v2/stock/products",
            headers=headers,
            json={
                "reference_base": "TEST-RECO",
                "name": "Article recommandation",
                "material_type": "PVC",
                "unit": "pce",
                "supplier": "Fournisseur test",
                "variants": [
                    {
                        "reference": "TEST-RECO-LOW",
                        "color": "Bas",
                        "cost_price": 10,
                        "quantity_in_stock": 2,
                        "min_threshold": 5,
                    },
                    {
                        "reference": "TEST-RECO-OK",
                        "color": "OK",
                        "cost_price": 10,
                        "quantity_in_stock": 12,
                        "min_threshold": 5,
                    },
                ],
            },
        )
        assert product_response.status_code == 200, product_response.text
        low_variant_id = product_response.json()["variants"][0]["id"]

        recommendations_response = client.get("/v2/purchases/ai-recommendations", headers=headers)
        assert recommendations_response.status_code == 200, recommendations_response.text
        recommendations = recommendations_response.json()
        assert len(recommendations) == 1
        assert recommendations[0]["variant_id"] == low_variant_id
        assert recommendations[0]["reference"] == "TEST-RECO-LOW"
        assert recommendations[0]["current_stock"] == 2.0
        assert recommendations[0]["suggested_quantity"] == 8.0
        assert "seuil configuré" in recommendations[0]["reason"]
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def test_purchase_need_recommendation_is_created_when_stock_is_below_threshold(purchase_test_client):
    client, TestingSessionLocal = purchase_test_client
    headers = _auth_headers(TestingSessionLocal, "purchase-need-tester")

    with TestingSessionLocal() as db:
        variant_id = _seed_purchase_need_variant(
            db,
            reference="NEED-LOW-STOCK",
            supplier="CORTIZO",
            physical_quantity=2,
            min_threshold=5,
        )

    response = client.get("/v2/purchases/ai-recommendations", headers=headers)

    assert response.status_code == 200, response.text
    needs = response.json()
    assert len(needs) == 1
    assert needs[0]["variant_id"] == variant_id
    assert needs[0]["reference"] == "NEED-LOW-STOCK"
    assert needs[0]["current_stock"] == 2.0
    assert needs[0]["suggested_quantity"] == 8.0
    assert "seuil configuré" in needs[0]["reason"]


def test_purchase_need_recommendation_is_not_created_when_available_stock_is_ok(purchase_test_client):
    client, TestingSessionLocal = purchase_test_client
    headers = _auth_headers(TestingSessionLocal, "purchase-ok-tester")

    with TestingSessionLocal() as db:
        _seed_purchase_need_variant(
            db,
            reference="NEED-STOCK-OK",
            supplier="CORTIZO",
            physical_quantity=8,
            min_threshold=5,
        )

    response = client.get("/v2/purchases/ai-recommendations", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json() == []


def test_purchase_need_recommendation_excludes_draft_catalog_items(purchase_test_client):
    client, TestingSessionLocal = purchase_test_client
    headers = _auth_headers(TestingSessionLocal, "purchase-draft-tester")

    with TestingSessionLocal() as db:
        _seed_purchase_need_variant(
            db,
            reference="NEED-DRAFT",
            supplier="SEPALUMIC",
            catalog_status="DRAFT",
            physical_quantity=0,
            min_threshold=5,
        )

    response = client.get("/v2/purchases/needs", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["needs"] == []


def test_purchase_need_recommendation_flags_blocked_supplier_as_not_orderable(purchase_test_client):
    client, TestingSessionLocal = purchase_test_client
    headers = _auth_headers(TestingSessionLocal, "purchase-blocked-supplier-tester")

    with TestingSessionLocal() as db:
        variant_id = _seed_purchase_need_variant(
            db,
            reference="NEED-BLOCKED-SUPPLIER",
            supplier="Fournisseur bloqué",
            supplier_status="BLOCKED",
            physical_quantity=0,
            min_threshold=5,
        )

    response = client.get("/v2/purchases/needs", headers=headers)

    assert response.status_code == 200, response.text
    [need] = [item for item in response.json()["needs"] if item["variant_id"] == variant_id]
    assert need["supplier"] == "Fournisseur bloqué"
    assert need["is_orderable"] is False
    assert need["blocked_reason"] == "Fournisseur bloqué."


def test_purchase_need_recommendations_expose_supplier_group_priority_and_net_need(purchase_test_client):
    client, TestingSessionLocal = purchase_test_client
    headers = _auth_headers(TestingSessionLocal, "purchase-group-priority-tester")

    with TestingSessionLocal() as db:
        critical_variant_id = _seed_purchase_need_variant(
            db,
            reference="NEED-CRITICAL",
            supplier="CORTIZO",
            physical_quantity=0,
            min_threshold=5,
        )
        urgent_variant_id = _seed_purchase_need_variant(
            db,
            reference="NEED-URGENT",
            supplier="CORTIZO",
            physical_quantity=3,
            min_threshold=5,
        )

    response = client.get("/v2/purchases/needs", headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    by_variant = {item["variant_id"]: item for item in payload["needs"]}
    assert by_variant[critical_variant_id]["supplier"] == "CORTIZO"
    assert by_variant[critical_variant_id]["priority"] == "CRITICAL"
    assert by_variant[critical_variant_id]["net_need_quantity"] == 10.0
    assert by_variant[urgent_variant_id]["priority"] == "URGENT"
    assert by_variant[urgent_variant_id]["net_need_quantity"] == 7.0
    [group] = [item for item in payload["groups"] if item["supplier"] == "CORTIZO"]
    assert group["critical_count"] == 1
    assert group["urgent_count"] == 1
    assert group["is_orderable"] is True


def test_purchase_order_direct_creation_requires_order_permission(purchase_test_client):
    client, TestingSessionLocal = purchase_test_client
    headers = _auth_headers(TestingSessionLocal, "magasinier-no-order", role="MAGASINIER")

    with TestingSessionLocal() as db:
        variant_id = _seed_purchase_need_variant(
            db,
            reference="REQ-NO-DIRECT-ORDER",
            supplier="CORTIZO",
            physical_quantity=0,
            min_threshold=5,
        )

    response = client.post(
        "/v2/purchases/",
        headers=headers,
        json={
            "supplier": "CORTIZO",
            "lines": [{"variant_id": variant_id, "quantity": 1, "unit_price": 10}],
        },
    )

    assert response.status_code == 403
    assert "purchases.order" in response.json()["detail"]


def test_sensitive_purchase_order_requires_purchase_request_validation(purchase_test_client):
    client, TestingSessionLocal = purchase_test_client

    with TestingSessionLocal() as db:
        _grant_role_permissions(db, "ACHATS", ["purchases.order"])
        variant_id = _seed_purchase_need_variant(
            db,
            reference="REQ-SENSITIVE-LOCK",
            supplier="CORTIZO",
            physical_quantity=0,
            min_threshold=5,
        )

    headers = _auth_headers(TestingSessionLocal, "buyer-sensitive-lock", role="ACHATS")

    response = client.post(
        "/v2/purchases/",
        headers=headers,
        json={
            "supplier": "CORTIZO",
            "lines": [{"variant_id": variant_id, "quantity": 2, "unit_price": 600}],
        },
    )

    assert response.status_code == 409
    assert "Demande d'achat obligatoire" in response.json()["detail"]


def test_purchase_request_can_be_approved_and_converted_to_order(purchase_test_client):
    client, TestingSessionLocal = purchase_test_client

    with TestingSessionLocal() as db:
        _grant_role_permissions(db, "MAGASINIER", ["purchases.request"])
        _grant_role_permissions(db, "ACHATS", ["purchases.approve", "purchases.order"])
        variant_id = _seed_purchase_need_variant(
            db,
            reference="REQ-APPROVE-CONVERT",
            supplier="CORTIZO",
            physical_quantity=0,
            min_threshold=5,
        )

    request_headers = _auth_headers(TestingSessionLocal, "magasinier-requester", role="MAGASINIER")
    approval_headers = _auth_headers(TestingSessionLocal, "buyer-approver", role="ACHATS")

    create_response = client.post(
        "/v2/purchases/requests",
        headers=request_headers,
        json={
            "supplier": "CORTIZO",
            "notes": "Rupture atelier",
            "sensitivity_reason": "Achat sensible validé par achats",
            "lines": [{"variant_id": variant_id, "quantity": 4, "unit_price": 12.5}],
        },
    )
    assert create_response.status_code == 200, create_response.text
    request_payload = create_response.json()
    assert request_payload["reference"].startswith("PR-")
    assert request_payload["status"] == "PENDING_APPROVAL"
    assert request_payload["total_amount"] == 50.0
    request_id = request_payload["id"]

    approve_response = client.post(f"/v2/purchases/requests/{request_id}/approve", headers=approval_headers)
    assert approve_response.status_code == 200, approve_response.text
    assert approve_response.json()["status"] == "APPROVED"
    assert approve_response.json()["approved_by"] == "buyer-approver"

    convert_response = client.post(f"/v2/purchases/requests/{request_id}/convert", headers=approval_headers)
    assert convert_response.status_code == 200, convert_response.text
    converted = convert_response.json()
    assert converted["request"]["status"] == "CONVERTED"
    assert converted["purchase_order"]["reference"].startswith("PO-")

    orders_response = client.get("/v2/purchases/", headers=approval_headers)
    assert orders_response.status_code == 200, orders_response.text
    [po] = [item for item in orders_response.json() if item["id"] == converted["purchase_order"]["id"]]
    assert po["supplier"] == "CORTIZO"
    assert po["total_amount"] == 50.0

    second_convert_response = client.post(f"/v2/purchases/requests/{request_id}/convert", headers=approval_headers)
    assert second_convert_response.status_code == 200, second_convert_response.text
    assert second_convert_response.json()["purchase_order"]["id"] == converted["purchase_order"]["id"]


def test_supplier_dispute_can_be_opened_and_resolved_on_purchase_order(purchase_test_client):
    client, TestingSessionLocal = purchase_test_client

    with TestingSessionLocal() as db:
        _grant_role_permissions(
            db,
            "ACHATS",
            [
                "purchases.order",
                "purchases.receive",
                "purchases.approve",
                "purchases.invoice.manage",
            ],
        )
        variant_id = _seed_purchase_need_variant(
            db,
            reference="REQ-DISPUTE",
            supplier="CORTIZO",
            physical_quantity=0,
            min_threshold=5,
        )

    headers = _auth_headers(TestingSessionLocal, "buyer-dispute", role="ACHATS")
    po_response = client.post(
        "/v2/purchases/",
        headers=headers,
        json={
            "supplier": "CORTIZO",
            "lines": [{"variant_id": variant_id, "quantity": 1, "unit_price": 10}],
        },
    )
    assert po_response.status_code == 200, po_response.text
    po_id = po_response.json()["id"]

    dispute_response = client.post(
        "/v2/purchases/disputes",
        headers=headers,
        json={
            "supplier": "CORTIZO",
            "purchase_order_id": po_id,
            "title": "Écart quantité réception",
            "category": "QUANTITY",
            "severity": "HIGH",
            "description": "La quantité reçue ne correspond pas au bon.",
            "expected_quantity": 1,
            "received_quantity": 0,
            "expected_action": "REDELIVER",
            "blocks_receipt": True,
            "blocks_payment": True,
            "impact_summary": "Chantier bloqué tant que la pièce manque.",
        },
    )
    assert dispute_response.status_code == 200, dispute_response.text
    dispute = dispute_response.json()
    assert dispute["reference"].startswith("LIT-")
    assert dispute["status"] == "OPEN"
    assert dispute["expected_action"] == "REDELIVER"
    assert dispute["blocks_receipt"] is True
    assert dispute["blocks_payment"] is True

    details = client.get(f"/v2/purchases/{po_id}", headers=headers).json()
    assert details["disputes"][0]["reference"] == dispute["reference"]
    assert details["disputes"][0]["impact_summary"] == "Chantier bloqué tant que la pièce manque."

    blocked_receipt = client.post(
        f"/v2/purchases/{po_id}/receive",
        headers=headers,
        json={"target_location_id": 1},
    )
    assert blocked_receipt.status_code == 409
    assert "Réception bloquée" in blocked_receipt.json()["detail"]

    blocked_invoice = client.post(
        f"/v2/purchases/{po_id}/supplier-invoices",
        headers=headers,
        json={
            "supplier_reference": "FAC-BLOCKED",
            "lines": [],
        },
    )
    assert blocked_invoice.status_code == 409
    assert "Rapprochement facture bloqué" in blocked_invoice.json()["detail"]

    start_response = client.post(
        f"/v2/purchases/disputes/{dispute['id']}/start",
        headers=headers,
    )
    assert start_response.status_code == 200, start_response.text
    assert start_response.json()["status"] == "IN_PROGRESS"

    blocked_resolution = client.post(
        f"/v2/purchases/disputes/{dispute['id']}/resolve",
        headers=headers,
        json={"resolution_notes": "Avoir fournisseur obtenu."},
    )
    assert blocked_resolution.status_code == 400
    assert "preuve est obligatoire" in blocked_resolution.json()["detail"]

    upload_response = client.post(
        f"/v2/purchases/disputes/{dispute['id']}/attachments",
        headers=headers,
        files={"file": ("preuve-litige.txt", b"Photo BL + commentaire reception", "text/plain")},
    )
    assert upload_response.status_code == 200, upload_response.text
    dispute_with_attachment = upload_response.json()
    assert dispute_with_attachment["attachments"][0]["original_filename"] == "preuve-litige.txt"
    assert any(event["event_type"] == "ATTACHMENT_ADDED" for event in dispute_with_attachment["events"])

    download_response = client.get(
        f"/v2/purchases/disputes/{dispute['id']}/attachments/{dispute_with_attachment['attachments'][0]['id']}/download",
        headers=headers,
    )
    assert download_response.status_code == 200, download_response.text
    assert download_response.content == b"Photo BL + commentaire reception"

    resolve_response = client.post(
        f"/v2/purchases/disputes/{dispute['id']}/resolve",
        headers=headers,
        json={"resolution_notes": "Avoir fournisseur obtenu."},
    )
    assert resolve_response.status_code == 200, resolve_response.text
    assert resolve_response.json()["status"] == "RESOLVED"
    assert any(event["event_type"] == "RESOLVED" for event in resolve_response.json()["events"])


def test_purchase_request_rejection_requires_reason(purchase_test_client):
    client, TestingSessionLocal = purchase_test_client

    with TestingSessionLocal() as db:
        _grant_role_permissions(db, "MAGASINIER", ["purchases.request"])
        _grant_role_permissions(db, "ACHATS", ["purchases.approve"])
        variant_id = _seed_purchase_need_variant(
            db,
            reference="REQ-REJECT",
            supplier="CORTIZO",
            physical_quantity=0,
            min_threshold=5,
        )

    request_headers = _auth_headers(TestingSessionLocal, "magasinier-reject-request", role="MAGASINIER")
    approval_headers = _auth_headers(TestingSessionLocal, "buyer-reject", role="ACHATS")

    create_response = client.post(
        "/v2/purchases/requests",
        headers=request_headers,
        json={
            "supplier": "CORTIZO",
            "lines": [{"variant_id": variant_id, "quantity": 1, "unit_price": 10}],
        },
    )
    request_id = create_response.json()["id"]

    empty_reason = client.post(
        f"/v2/purchases/requests/{request_id}/reject",
        headers=approval_headers,
        json={"reason": "   "},
    )
    assert empty_reason.status_code == 400

    reject_response = client.post(
        f"/v2/purchases/requests/{request_id}/reject",
        headers=approval_headers,
        json={"reason": "Prix à renégocier"},
    )
    assert reject_response.status_code == 200, reject_response.text
    assert reject_response.json()["status"] == "REJECTED"
    assert reject_response.json()["rejection_reason"] == "Prix à renégocier"


def test_purchase_request_keeps_procurement_need_context(purchase_test_client):
    client, TestingSessionLocal = purchase_test_client
    headers = _auth_headers(TestingSessionLocal, "need-context-requester")

    with TestingSessionLocal() as db:
        variant_id = _seed_purchase_need_variant(
            db,
            reference="REQ-NEED-CONTEXT",
            supplier="CORTIZO",
            physical_quantity=0,
            min_threshold=5,
        )

    needs_response = client.get("/v2/purchases/needs", headers=headers)
    assert needs_response.status_code == 200, needs_response.text
    [need] = [item for item in needs_response.json()["needs"] if item["variant_id"] == variant_id]
    assert need["priority"] == "CRITICAL"
    assert need["net_need_quantity"] == 10.0

    create_response = client.post(
        "/v2/purchases/requests",
        headers=headers,
        json={
            "supplier": "CORTIZO",
            "notes": "Besoin automatique depuis seuil stock",
            "lines": [{
                "variant_id": variant_id,
                "quantity": need["suggested_quantity"],
                "unit_price": 12,
                "need_priority": need["priority"],
                "need_reason": need["reason"],
            }],
        },
    )

    assert create_response.status_code == 200, create_response.text
    request_payload = create_response.json()
    assert request_payload["lines"][0]["need_priority"] == "CRITICAL"
    assert "Disponible nul" in request_payload["lines"][0]["need_reason"]

    updated_needs_response = client.get("/v2/purchases/needs", headers=headers)
    assert updated_needs_response.status_code == 200, updated_needs_response.text
    [updated_need] = [item for item in updated_needs_response.json()["needs"] if item["variant_id"] == variant_id]
    assert updated_need["open_purchase_request_quantity"] == 10.0
    assert updated_need["net_need_quantity"] == 0.0
    assert updated_need["priority"] == "COVERED"
    assert "OPEN_PURCHASE_REQUEST" in updated_need["origins"]


def test_purchase_request_refuses_duplicate_open_need_line(purchase_test_client):
    client, TestingSessionLocal = purchase_test_client
    headers = _auth_headers(TestingSessionLocal, "need-duplicate-requester")

    with TestingSessionLocal() as db:
        variant_id = _seed_purchase_need_variant(
            db,
            reference="REQ-DUPLICATE-NEED",
            supplier="CORTIZO",
            physical_quantity=0,
            min_threshold=5,
        )

    payload = {
        "supplier": "CORTIZO",
        "lines": [{"variant_id": variant_id, "quantity": 4, "unit_price": 10}],
    }
    first_response = client.post("/v2/purchases/requests", headers=headers, json=payload)
    assert first_response.status_code == 200, first_response.text

    duplicate_response = client.post("/v2/purchases/requests", headers=headers, json=payload)
    assert duplicate_response.status_code == 409
    assert "REQ-DUPLICATE-NEED" in duplicate_response.json()["detail"]

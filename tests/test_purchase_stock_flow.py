from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import database, models
from backend.core import security
from backend.main import app


def _auth_headers(session_factory, username: str, role: str = "ADMIN") -> dict:
    """Crée l'utilisateur en base si besoin, puis émet un JWT valide pour lui."""
    with session_factory() as db:
        if not db.query(models.User).filter(models.User.username == username).first():
            db.add(models.User(username=username, pin_hash="test-pin", role=role, is_active=True))
            db.commit()
    token = security.create_access_token({"sub": username, "role": role})
    return {"Authorization": f"Bearer {token}"}


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
            json={"name": "WH/Réception partielle", "usage": "internal"},
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

        invoice_response = client.post(
            f"/v2/purchases/{po_id}/supplier-invoices",
            headers=headers,
            json={
                "supplier_reference": "FAC-PARTIAL",
                "lines": [{"purchase_order_line_id": line_id, "quantity": 2}],
            },
        )
        assert invoice_response.status_code == 200, invoice_response.text
        supplier_invoice = invoice_response.json()
        assert supplier_invoice["reference"].startswith("FF-")
        assert supplier_invoice["supplier_reference"] == "FAC-PARTIAL"
        assert supplier_invoice["total_amount"] == 20.0

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

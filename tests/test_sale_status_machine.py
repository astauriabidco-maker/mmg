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


def _make_test_client():
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
    return engine, TestingSessionLocal, TestClient(app)


def _cleanup_test_client(engine):
    app.dependency_overrides.pop(database.get_db, None)
    models.Base.metadata.drop_all(bind=engine)


def _create_sale(db, status: str, reference: str = "DEV-STATUT") -> int:
    sale = models.SaleOrder(
        reference=reference,
        client_name="Client statuts",
        status=status,
        tax_rate=20,
    )
    db.add(sale)
    db.flush()
    db.add(
        models.SaleOrderLine(
            order_id=sale.id,
            description="Menuiserie ALU",
            quantity=1,
            unit_price=1000,
        )
    )
    db.commit()
    return sale.id


def test_unknown_target_status_is_rejected():
    engine, TestingSessionLocal, client = _make_test_client()
    try:
        with TestingSessionLocal() as db:
            sale_id = _create_sale(db, "DRAFT")

        headers = _auth_headers(TestingSessionLocal, "statuts-admin")
        response = client.put(f"/v2/sales/{sale_id}/status", params={"status": "INVOICED"}, headers=headers)

        assert response.status_code == 400
        assert "Statut cible inconnu" in response.text

        with TestingSessionLocal() as db:
            assert db.query(models.SaleOrder).one().status == "DRAFT"
    finally:
        _cleanup_test_client(engine)


def test_arbitrary_transition_is_rejected():
    engine, TestingSessionLocal, client = _make_test_client()
    try:
        with TestingSessionLocal() as db:
            sale_id = _create_sale(db, "DRAFT")

        headers = _auth_headers(TestingSessionLocal, "statuts-admin")
        response = client.put(f"/v2/sales/{sale_id}/status", params={"status": "DELIVERED"}, headers=headers)

        assert response.status_code == 400
        assert "Transition de statut interdite" in response.text
        assert "DRAFT → DELIVERED" in response.text

        with TestingSessionLocal() as db:
            assert db.query(models.SaleOrder).one().status == "DRAFT"
    finally:
        _cleanup_test_client(engine)


def test_status_change_requires_admin_or_manager_role():
    engine, TestingSessionLocal, client = _make_test_client()
    try:
        with TestingSessionLocal() as db:
            sale_id = _create_sale(db, "DRAFT")

        headers = _auth_headers(TestingSessionLocal, "statuts-vendeur", role="SELLER")
        response = client.put(f"/v2/sales/{sale_id}/status", params={"status": "SENT"}, headers=headers)

        assert response.status_code == 403

        with TestingSessionLocal() as db:
            assert db.query(models.SaleOrder).one().status == "DRAFT"
    finally:
        _cleanup_test_client(engine)


def test_ready_for_prod_requires_active_workshop_reservation():
    engine, TestingSessionLocal, client = _make_test_client()
    try:
        with TestingSessionLocal() as db:
            sale_id = _create_sale(db, "VALIDATED")

        headers = _auth_headers(TestingSessionLocal, "statuts-admin")

        refused = client.put(f"/v2/sales/{sale_id}/status", params={"status": "READY_FOR_PROD"}, headers=headers)
        assert refused.status_code == 400
        assert "réservation atelier active" in refused.text

        with TestingSessionLocal() as db:
            assert db.query(models.SaleOrder).one().status == "VALIDATED"
            reservation = models.StockReservation(
                reference="RSV-GARDE-FOU",
                sale_order_id=sale_id,
                status="reserved",
                source_label="SEPVER.TXT",
                created_by="test",
            )
            db.add(reservation)
            db.flush()
            db.add(
                models.StockReservationLine(
                    reservation_id=reservation.id,
                    supplier="SEPALUMIC",
                    supplier_reference="7007",
                    designation="Profil atelier",
                    unit="barre",
                    requested_quantity=1,
                    reserved_quantity=1,
                    status="reserved",
                )
            )
            db.commit()

        accepted = client.put(f"/v2/sales/{sale_id}/status", params={"status": "READY_FOR_PROD"}, headers=headers)
        assert accepted.status_code == 200, accepted.text

        with TestingSessionLocal() as db:
            assert db.query(models.SaleOrder).one().status == "READY_FOR_PROD"
    finally:
        _cleanup_test_client(engine)


def test_terminal_statuses_cannot_move_back():
    engine, TestingSessionLocal, client = _make_test_client()
    try:
        with TestingSessionLocal() as db:
            delivered_id = _create_sale(db, "DELIVERED", reference="DEV-LIVRE")
            cancelled_id = _create_sale(db, "CANCELLED", reference="DEV-ANNULE")

        headers = _auth_headers(TestingSessionLocal, "statuts-admin")

        delivered_response = client.put(f"/v2/sales/{delivered_id}/status", params={"status": "VALIDATED"}, headers=headers)
        assert delivered_response.status_code == 400
        assert "terminal" in delivered_response.text

        cancelled_response = client.put(f"/v2/sales/{cancelled_id}/status", params={"status": "SENT"}, headers=headers)
        assert cancelled_response.status_code == 400
        assert "terminal" in cancelled_response.text

        with TestingSessionLocal() as db:
            statuses = {sale.reference: sale.status for sale in db.query(models.SaleOrder).all()}
        assert statuses == {"DEV-LIVRE": "DELIVERED", "DEV-ANNULE": "CANCELLED"}
    finally:
        _cleanup_test_client(engine)


def test_in_production_cancellation_is_admin_only():
    engine, TestingSessionLocal, client = _make_test_client()
    try:
        with TestingSessionLocal() as db:
            sale_id = _create_sale(db, "IN_PRODUCTION")

        manager_headers = _auth_headers(TestingSessionLocal, "statuts-manager", role="MANAGER")
        refused = client.put(f"/v2/sales/{sale_id}/status", params={"status": "CANCELLED"}, headers=manager_headers)
        assert refused.status_code == 403
        assert "administrateur" in refused.text

        admin_headers = _auth_headers(TestingSessionLocal, "statuts-admin")
        accepted = client.put(f"/v2/sales/{sale_id}/status", params={"status": "CANCELLED"}, headers=admin_headers)
        assert accepted.status_code == 200, accepted.text

        with TestingSessionLocal() as db:
            assert db.query(models.SaleOrder).one().status == "CANCELLED"
    finally:
        _cleanup_test_client(engine)


def test_valid_commercial_transitions_still_work():
    engine, TestingSessionLocal, client = _make_test_client()
    try:
        with TestingSessionLocal() as db:
            sale_id = _create_sale(db, "DRAFT")

        headers = _auth_headers(TestingSessionLocal, "statuts-admin")

        sent = client.put(f"/v2/sales/{sale_id}/status", params={"status": "SENT"}, headers=headers)
        assert sent.status_code == 200, sent.text
        assert sent.json()["portal_link"]

        validated = client.put(f"/v2/sales/{sale_id}/status", params={"status": "VALIDATED"}, headers=headers)
        assert validated.status_code == 200, validated.text

        in_design = client.put(f"/v2/sales/{sale_id}/status", params={"status": "IN_DESIGN"}, headers=headers)
        assert in_design.status_code == 200, in_design.text

        with TestingSessionLocal() as db:
            sale_db = db.query(models.SaleOrder).one()
        assert sale_db.status == "IN_DESIGN"
        assert sale_db.signature_token
    finally:
        _cleanup_test_client(engine)


def test_same_status_is_idempotent_noop():
    engine, TestingSessionLocal, client = _make_test_client()
    try:
        with TestingSessionLocal() as db:
            sale_id = _create_sale(db, "DRAFT")

        headers = _auth_headers(TestingSessionLocal, "statuts-admin")
        response = client.put(f"/v2/sales/{sale_id}/status", params={"status": "DRAFT"}, headers=headers)

        assert response.status_code == 200, response.text
        assert "Statut inchangé" in response.json()["message"]

        with TestingSessionLocal() as db:
            sale_db = db.query(models.SaleOrder).one()
        assert sale_db.status == "DRAFT"
        assert sale_db.signature_token is None
    finally:
        _cleanup_test_client(engine)

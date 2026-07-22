"""Durcissement API stock (vague audit inventaire).

Couvre :
- l'authentification exigée sur les exports et lectures sensibles (401 sans token) ;
- les permissions métier sur les exports (403 sans la permission, 200 avec) ;
- l'export de campagne réservé à ``inventory.validate`` (comptage aveugle) ;
- le gel de zone hérité : campagne sur un entrepôt parent → mouvement sur un
  emplacement enfant bloqué (423) ;
- l'enrichissement de ``GET /transactions`` (ids et noms source/destination) ;
- le réservé/disponible PAR EMPLACEMENT exposé par ``GET /quants``.
"""
from __future__ import annotations

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


def _headers(session_factory, username: str, role: str = "ADMIN") -> dict:
    with session_factory() as db:
        if not db.query(models.User).filter(models.User.username == username).first():
            db.add(models.User(username=username, pin_hash="test-pin", role=role, is_active=True))
            db.commit()
    token = security.create_access_token({"sub": username, "role": role})
    return {"Authorization": f"Bearer {token}"}


def _seed_role(session_factory, role_name: str, permission_codes: list[str]) -> None:
    """Crée un rôle avec exactement les permissions données (matrice réelle,
    contrairement au short-circuit ADMIN de ``user_has_permission``)."""
    with session_factory() as db:
        role = db.query(models.Role).filter_by(name=role_name).first()
        if not role:
            role = models.Role(name=role_name, description=f"Rôle test {role_name}")
            db.add(role)
            db.flush()
        for code in permission_codes:
            permission = db.query(models.Permission).filter_by(code=code).first()
            if not permission:
                permission = models.Permission(code=code, module="Tests", description=f"Permission test {code}")
                db.add(permission)
                db.flush()
            if permission not in role.permissions:
                role.permissions.append(permission)
        db.commit()


def _seed_product_variant(db, reference: str = "HARD-001") -> int:
    product = models.Product(
        reference_base=reference,
        name="Article durcissement",
        material_type="ACCESSOIRE",
        unit="pce",
        supplier="MMG",
        product_type="stockable",
        catalog_status="ACTIVE",
    )
    db.add(product)
    db.flush()
    variant = models.ProductVariant(
        product_id=product.id,
        reference=f"{reference}-STD",
        cost_price=10,
        quantity_in_stock=0,
        min_threshold=0,
    )
    db.add(variant)
    db.commit()
    return variant.id


def _seed_location_tree(db):
    """Entrepôt parent > rack enfant, plus un second entrepôt hors zone."""
    parent = models.StockLocation(name="TEST/Entrepôt parent", usage="internal", is_active=True)
    child = models.StockLocation(name="TEST/Rack enfant", usage="internal", is_active=True)
    other = models.StockLocation(name="TEST/Autre entrepôt", usage="internal", is_active=True)
    db.add_all([parent, child, other])
    db.flush()
    child.parent_id = parent.id
    db.commit()
    return parent.id, child.id, other.id


# ---------------------------------------------------------------------------
# m1 + C1 : authentification et permissions sur les endpoints sensibles
# ---------------------------------------------------------------------------


def test_sensitive_endpoints_reject_anonymous(stock_client):
    client, _ = stock_client
    for path in [
        "/v2/stock/export/inventory",
        "/v2/stock/catalog/drafts/export",
        "/v2/stock/transactions",
        "/v2/stock/quants",
        "/v2/stock/locations",
        "/v2/stock/chatter/variant/1",
    ]:
        response = client.get(path)
        assert response.status_code == 401, f"{path} accessible sans token"


def test_export_inventory_requires_stock_adjust_permission(stock_client):
    client, TestingSessionLocal = stock_client
    _seed_role(TestingSessionLocal, "MAGASINIER", ["inventory.count", "stock.receive"])
    magasinier = _headers(TestingSessionLocal, "hardening-magasinier", role="MAGASINIER")
    admin = _headers(TestingSessionLocal, "hardening-admin", role="ADMIN")

    forbidden = client.get("/v2/stock/export/inventory", headers=magasinier)
    assert forbidden.status_code == 403

    allowed = client.get("/v2/stock/export/inventory", headers=admin)
    assert allowed.status_code == 200
    assert "spreadsheetml" in allowed.headers["content-type"]


def test_drafts_export_requires_catalog_qualify_permission(stock_client):
    client, TestingSessionLocal = stock_client
    _seed_role(TestingSessionLocal, "MAGASINIER", ["inventory.count", "stock.receive"])
    magasinier = _headers(TestingSessionLocal, "hardening-magasinier", role="MAGASINIER")
    admin = _headers(TestingSessionLocal, "hardening-admin", role="ADMIN")

    forbidden = client.get("/v2/stock/catalog/drafts/export", headers=magasinier)
    assert forbidden.status_code == 403

    allowed = client.get("/v2/stock/catalog/drafts/export", headers=admin)
    assert allowed.status_code == 200
    assert "spreadsheetml" in allowed.headers["content-type"]


# ---------------------------------------------------------------------------
# C2 : export de campagne réservé à inventory.validate (comptage aveugle)
# ---------------------------------------------------------------------------


def test_inventory_session_export_requires_validate_permission(stock_client):
    client, TestingSessionLocal = stock_client
    _seed_role(TestingSessionLocal, "MAGASINIER", ["inventory.count", "stock.receive"])
    admin = _headers(TestingSessionLocal, "hardening-admin", role="ADMIN")
    magasinier = _headers(TestingSessionLocal, "hardening-magasinier", role="MAGASINIER")

    with TestingSessionLocal() as db:
        variant_id = _seed_product_variant(db)
        parent_id, child_id, _other_id = _seed_location_tree(db)

    session_response = client.post(
        "/v2/stock/inventory-sessions",
        headers=admin,
        json={
            "name": "Campagne aveugle export",
            "location_id": parent_id,
            "blind_counting": True,
        },
    )
    assert session_response.status_code == 200, session_response.text
    session_id = session_response.json()["id"]

    # Le compteur (inventory.count sans inventory.validate) ne peut pas
    # s'exporter les espérés pendant une campagne aveugle ouverte.
    forbidden = client.get(f"/v2/stock/inventory-sessions/{session_id}/export", headers=magasinier)
    assert forbidden.status_code == 403

    allowed = client.get(f"/v2/stock/inventory-sessions/{session_id}/export", headers=admin)
    assert allowed.status_code == 200
    assert "spreadsheetml" in allowed.headers["content-type"]


# ---------------------------------------------------------------------------
# M2 : gel de zone hérité sur les sous-emplacements
# ---------------------------------------------------------------------------


def test_zone_lock_on_parent_blocks_move_on_child_location(stock_client):
    client, TestingSessionLocal = stock_client
    admin = _headers(TestingSessionLocal, "hardening-admin", role="ADMIN")

    with TestingSessionLocal() as db:
        variant_id = _seed_product_variant(db)
        parent_id, child_id, other_id = _seed_location_tree(db)

    # Campagne gelée sur l'entrepôt PARENT.
    session_response = client.post(
        "/v2/stock/inventory-sessions",
        headers=admin,
        json={"name": "Campagne gel parent", "location_id": parent_id},
    )
    assert session_response.status_code == 200, session_response.text
    session_id = session_response.json()["id"]
    assert session_response.json()["zone_locked"] is True

    # Réception sur l'emplacement ENFANT → bloquée (423).
    child_move = client.post(
        "/v2/stock/transaction",
        headers=admin,
        json={"variant_id": variant_id, "location_dest_id": child_id, "quantity": 3},
    )
    assert child_move.status_code == 423
    assert "Zone gelée" in child_move.json()["detail"]

    # Réception sur le parent lui-même → toujours bloquée (comportement existant).
    parent_move = client.post(
        "/v2/stock/transaction",
        headers=admin,
        json={"variant_id": variant_id, "location_dest_id": parent_id, "quantity": 3},
    )
    assert parent_move.status_code == 423

    # Réception sur un entrepôt hors zone → autorisée.
    other_move = client.post(
        "/v2/stock/transaction",
        headers=admin,
        json={"variant_id": variant_id, "location_dest_id": other_id, "quantity": 3},
    )
    assert other_move.status_code == 200, other_move.text

    # Campagne annulée → le mouvement sur l'enfant redevient possible.
    cancel = client.post(f"/v2/stock/inventory-sessions/{session_id}/cancel", headers=admin)
    assert cancel.status_code == 200, cancel.text
    unlocked_move = client.post(
        "/v2/stock/transaction",
        headers=admin,
        json={"variant_id": variant_id, "location_dest_id": child_id, "quantity": 3},
    )
    assert unlocked_move.status_code == 200, unlocked_move.text


# ---------------------------------------------------------------------------
# M3 : transactions enrichies (ids + noms source/destination)
# ---------------------------------------------------------------------------


def test_transactions_expose_location_ids_and_names(stock_client):
    client, TestingSessionLocal = stock_client
    admin = _headers(TestingSessionLocal, "hardening-admin", role="ADMIN")

    with TestingSessionLocal() as db:
        variant_id = _seed_product_variant(db, reference="HARD-TX")
        parent_id, child_id, _other_id = _seed_location_tree(db)

    move = client.post(
        "/v2/stock/transaction",
        headers=admin,
        json={"variant_id": variant_id, "location_dest_id": child_id, "quantity": 5},
    )
    assert move.status_code == 200, move.text

    transactions = client.get("/v2/stock/transactions", headers=admin)
    assert transactions.status_code == 200, transactions.text
    rows = [row for row in transactions.json() if row["variant_id"] == variant_id]
    assert rows, "mouvement absent de /transactions"
    row = rows[0]
    assert row["location_id"] is None  # réception fournisseur : source virtuelle
    assert row["location_dest_id"] == child_id
    assert row["location_from_name"] is None
    assert row["location_to_name"] == "TEST/Rack enfant"

    # Transfert interne enfant → parent : les deux côtés sont renseignés.
    transfer = client.post(
        "/v2/stock/transaction",
        headers=admin,
        json={
            "variant_id": variant_id,
            "location_id": child_id,
            "location_dest_id": parent_id,
            "quantity": 2,
        },
    )
    assert transfer.status_code == 200, transfer.text
    transactions = client.get("/v2/stock/transactions", headers=admin)
    row = transactions.json()[0]
    assert row["location_id"] == child_id
    assert row["location_dest_id"] == parent_id
    assert row["location_from_name"] == "TEST/Rack enfant"
    assert row["location_to_name"] == "TEST/Entrepôt parent"


# ---------------------------------------------------------------------------
# M4 : réservé / disponible PAR EMPLACEMENT sur /quants
# ---------------------------------------------------------------------------


def test_quants_expose_reserved_and_available_per_location(stock_client):
    client, TestingSessionLocal = stock_client
    admin = _headers(TestingSessionLocal, "hardening-admin", role="ADMIN")

    with TestingSessionLocal() as db:
        variant_id = _seed_product_variant(db, reference="HARD-RES")
        wh = models.StockLocation(name="TEST/WH réservé", usage="internal", is_active=True)
        rack = models.StockLocation(name="TEST/Rack libre", usage="internal", is_active=True)
        customer = models.StockLocation(name="TEST/Client", usage="customer", is_active=True)
        db.add_all([wh, rack, customer])
        db.flush()
        db.add_all([
            models.StockQuant(variant_id=variant_id, location_id=wh.id, quantity=10),
            models.StockQuant(variant_id=variant_id, location_id=rack.id, quantity=5),
            models.StockQuant(variant_id=variant_id, location_id=customer.id, quantity=2),
        ])
        reservation = models.StockReservation(
            reference="RES-HARD-001",
            location_id=wh.id,
            status="reserved",
            created_by="test",
        )
        db.add(reservation)
        db.flush()
        db.add(models.StockReservationLine(
            reservation_id=reservation.id,
            variant_id=variant_id,
            requested_quantity=4,
            reserved_quantity=4,
            status="reserved",
        ))
        db.commit()
        wh_id, rack_id, customer_id = wh.id, rack.id, customer.id

    response = client.get("/v2/stock/quants", headers=admin)
    assert response.status_code == 200, response.text
    quants = {quant["location_id"]: quant for quant in response.json() if quant["variant_id"] == variant_id}

    # La réservation ancrée sur WH ne pèse que sur WH.
    assert quants[wh_id]["reserved_quantity"] == 4
    assert quants[wh_id]["available_quantity"] == 6
    assert quants[rack_id]["reserved_quantity"] == 0
    assert quants[rack_id]["available_quantity"] == 5
    # Emplacement non interne : champs non calculés (null).
    assert quants[customer_id]["reserved_quantity"] is None
    assert quants[customer_id]["available_quantity"] is None

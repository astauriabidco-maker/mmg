"""Réservations fermes ancrées sur un emplacement.

Couvre :
- l'ancrage ``location_id`` à la réservation (disponible calculé sur
  l'emplacement, plus sur tous les internes) ;
- le refus de sur-réservation dès qu'un second emplacement interne existe ;
- le re-contrôle à la consommation (stock pris entre-temps → 409 explicite) ;
- le retour client qui recrédite l'emplacement ancré.
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
from backend.services.stock_service import InventoryService


DEBIT_CONTENT = b"SEPALUMIC GAMME BASE\r\nVER TEST\r\nRAL;7007;BAVETTE DE FAITAGE;3;barre  6,50\r\n"


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


def _admin_headers(session_factory, username: str = "anchor-admin") -> dict:
    with session_factory() as db:
        if not db.query(models.User).filter(models.User.username == username).first():
            db.add(models.User(username=username, pin_hash="test-pin", role="ADMIN", is_active=True))
            db.commit()
    token = security.create_access_token({"sub": username, "role": "ADMIN"})
    return {"Authorization": f"Bearer {token}"}


def _seed_variant_with_two_locations(db, *, stock_wh: float = 0.0, stock_rack: float = 0.0):
    product = models.Product(
        reference_base="SEPALUMIC:7007",
        name="Bavette de faitage",
        material_type="ALU",
        unit="barre",
        supplier="SEPALUMIC",
        product_type="stockable",
    )
    db.add(product)
    db.flush()
    variant = models.ProductVariant(
        product_id=product.id,
        reference="SEPALUMIC:7007",
        supplier_reference="7007",
        quantity_in_stock=stock_wh + stock_rack,
        min_threshold=0,
    )
    wh = models.StockLocation(name="WH/Stock", usage="internal", is_active=True)
    rack = models.StockLocation(name="Rack ALU A", usage="internal", is_active=True)
    db.add_all([variant, wh, rack])
    db.flush()
    db.add(models.StockQuant(variant_id=variant.id, location_id=wh.id, quantity=stock_wh))
    db.add(models.StockQuant(variant_id=variant.id, location_id=rack.id, quantity=stock_rack))
    db.commit()
    return variant.id, wh.id, rack.id


def _seed_sale(db, reference: str, *, workflow_type: str | None = None, status: str = "VALIDATED") -> int:
    sale = models.SaleOrder(
        reference=reference,
        client_name="Client ancrage",
        status=status,
        workflow_type=workflow_type,
        tax_rate=20,
    )
    db.add(sale)
    db.flush()
    db.add(
        models.SaleOrderLine(
            order_id=sale.id,
            description="Menuiserie ALU Sepalumic",
            quantity=1,
            unit_price=1000,
        )
    )
    db.commit()
    return sale.id


def _reserve(client: TestClient, headers: dict, sale_id: int, source_location: str = "WH/Stock"):
    return client.post(
        "/v2/stock/workshop-debits/reservations",
        headers=headers,
        data={"sale_order_id": str(sale_id), "source_location": source_location},
        files=[("files", ("SEPVER.TXT", DEBIT_CONTENT, "text/plain"))],
    )


def test_reservation_is_anchored_to_source_location(stock_client):
    client, TestingSessionLocal = stock_client
    headers = _admin_headers(TestingSessionLocal)

    with TestingSessionLocal() as db:
        variant_id, wh_id, rack_id = _seed_variant_with_two_locations(db, stock_wh=0, stock_rack=5)
        sale_id = _seed_sale(db, "DEV-ANCRE-1")

    # Le stock est sur « Rack ALU A » : la prévisualisation sur WH/Stock voit
    # une pénurie (plus de disponible agrégé tous emplacements).
    preview_wh = client.post(
        "/v2/stock/workshop-debits/preview",
        headers=headers,
        data={"sale_order_id": str(sale_id), "source_location": "WH/Stock"},
        files=[("files", ("SEPVER.TXT", DEBIT_CONTENT, "text/plain"))],
    )
    assert preview_wh.status_code == 200, preview_wh.text
    assert preview_wh.json()["summary"]["stock_match_status"] == {"shortage": 1}

    preview_rack = client.post(
        "/v2/stock/workshop-debits/preview",
        headers=headers,
        data={"sale_order_id": str(sale_id), "source_location": "Rack ALU A"},
        files=[("files", ("SEPVER.TXT", DEBIT_CONTENT, "text/plain"))],
    )
    assert preview_rack.status_code == 200, preview_rack.text
    assert preview_rack.json()["summary"]["stock_match_status"] == {"ok": 1}

    reserve_response = _reserve(client, headers, sale_id, source_location="Rack ALU A")
    assert reserve_response.status_code == 200, reserve_response.text
    reservation = reserve_response.json()
    assert reservation["location_id"] == rack_id
    assert reservation["location_id"] != wh_id
    assert reservation["lines"][0]["reserved_quantity"] == 3

    consume_response = client.post(
        f"/v2/stock/workshop-debits/reservations/{reservation['id']}/consume",
        headers=headers,
    )
    assert consume_response.status_code == 200, consume_response.text

    with TestingSessionLocal() as db:
        rack_quant = db.query(models.StockQuant).filter_by(variant_id=variant_id, location_id=rack_id).one()
        wh_quant = db.query(models.StockQuant).filter_by(variant_id=variant_id, location_id=wh_id).one()
        production_quant = (
            db.query(models.StockQuant)
            .join(models.StockLocation)
            .filter(models.StockLocation.usage == "production")
            .one()
        )

    # La consommation a puisé sur l'emplacement ancré, pas sur WH/Stock.
    assert rack_quant.quantity == 2
    assert wh_quant.quantity == 0
    assert production_quant.quantity == 3


def test_over_reservation_is_refused_per_location(stock_client):
    client, TestingSessionLocal = stock_client
    headers = _admin_headers(TestingSessionLocal)

    with TestingSessionLocal() as db:
        _variant_id, wh_id, rack_id = _seed_variant_with_two_locations(db, stock_wh=5, stock_rack=5)
        sale_a = _seed_sale(db, "DEV-ANCRE-A")
        sale_b = _seed_sale(db, "DEV-ANCRE-B")
        sale_c = _seed_sale(db, "DEV-ANCRE-C")

    # Première réservation : 3 barres ancrées sur WH/Stock.
    first = _reserve(client, headers, sale_a, source_location="WH/Stock")
    assert first.status_code == 200, first.text
    assert first.json()["location_id"] == wh_id

    # Deuxième réservation de 3 sur le MÊME emplacement : refusée, même si le
    # physique global (5 + 5 = 10) couvrirait largement la demande.
    second = _reserve(client, headers, sale_b, source_location="WH/Stock")
    assert second.status_code == 400, second.text
    assert "Stock insuffisant" in second.text

    # Le second emplacement reste réservable indépendamment.
    third = _reserve(client, headers, sale_c, source_location="Rack ALU A")
    assert third.status_code == 200, third.text
    assert third.json()["location_id"] == rack_id


def test_consume_returns_409_when_stock_taken_in_between(stock_client):
    client, TestingSessionLocal = stock_client
    headers = _admin_headers(TestingSessionLocal)

    with TestingSessionLocal() as db:
        variant_id, wh_id, _rack_id = _seed_variant_with_two_locations(db, stock_wh=5, stock_rack=0)
        sale_id = _seed_sale(db, "DEV-ANCRE-409")

    reserve_response = _reserve(client, headers, sale_id, source_location="WH/Stock")
    assert reserve_response.status_code == 200, reserve_response.text
    reservation = reserve_response.json()

    # Un autre flux (vente comptoir, ajustement…) prélève 4 barres entre la
    # réservation et le débit : il ne reste qu'1 barre physique pour 3 réservées.
    with TestingSessionLocal() as db:
        customer = db.query(models.StockLocation).filter_by(name="Partner/Customer").first()
        if not customer:
            customer = models.StockLocation(name="Partner/Customer", usage="customer", is_active=True)
            db.add(customer)
            db.flush()
        InventoryService.move_stock(
            db,
            variant_id=variant_id,
            source_location_id=wh_id,
            dest_location_id=customer.id,
            quantity=4,
            reference="POS Out - TEST",
            source_screen="pos.checkout",
            document_type="pos_order",
            document_reference="TK-TEST",
        )
        db.commit()

    consume_response = client.post(
        f"/v2/stock/workshop-debits/reservations/{reservation['id']}/consume",
        headers=headers,
    )
    assert consume_response.status_code == 409, consume_response.text
    detail = consume_response.json()["detail"]
    assert "Stock insuffisant" in detail
    assert "WH/Stock" in detail
    assert "manquant 2" in detail

    # Rien n'a bougé : la réservation reste active et le stock intact.
    with TestingSessionLocal() as db:
        reservation_db = db.query(models.StockReservation).one()
        wh_quant = db.query(models.StockQuant).filter_by(variant_id=variant_id, location_id=wh_id).one()
        moves = db.query(models.StockMove).filter(models.StockMove.reference.like("DEBIT-ATELIER-%")).count()

    assert reservation_db.status == "reserved"
    assert wh_quant.quantity == 1
    assert moves == 0


def test_commercial_return_reintegrates_anchored_location(stock_client):
    client, TestingSessionLocal = stock_client
    headers = _admin_headers(TestingSessionLocal, username="anchor-sales")

    with TestingSessionLocal() as db:
        variant_id, wh_id, rack_id = _seed_variant_with_two_locations(db, stock_wh=5, stock_rack=0)
        sale = models.SaleOrder(
            reference="DEV-LIBRE-ANCRE",
            client_name="Client retour ancré",
            status="DRAFT",
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
                description="Bavette en stock",
                quantity=2,
                unit_price=25,
            )
        )
        db.commit()
        sale_id = sale.id

    # Validation + signature : crée la réservation commerciale ancrée.
    send_response = client.put(f"/v2/sales/{sale_id}/status", params={"status": "SENT"}, headers=headers)
    assert send_response.status_code == 200, send_response.text
    sale_response = client.get(f"/v2/sales/{sale_id}", headers=headers)
    token = sale_response.json()["signature_token"]
    sign_response = client.post(f"/v2/sales/portal/{token}/sign")
    assert sign_response.status_code == 200, sign_response.text

    with TestingSessionLocal() as db:
        reservation = db.query(models.StockReservation).one()
        assert reservation.location_id == wh_id
        reservation_id = reservation.id

    deliver_response = client.post(f"/v2/sales/{sale_id}/deliver-free-sale", headers=headers)
    assert deliver_response.status_code == 200, deliver_response.text

    # L'ancre est déplacée administrativement vers le rack (réorganisation
    # d'entrepôt) : le retour doit recréditer L'ANCRE, pas « WH/Stock » en dur.
    with TestingSessionLocal() as db:
        reservation = db.query(models.StockReservation).filter_by(id=reservation_id).one()
        reservation.location_id = rack_id
        db.commit()

    return_response = client.post(f"/v2/sales/{sale_id}/return-free-sale", headers=headers)
    assert return_response.status_code == 200, return_response.text

    with TestingSessionLocal() as db:
        wh_quant = db.query(models.StockQuant).filter_by(variant_id=variant_id, location_id=wh_id).one()
        rack_quant = db.query(models.StockQuant).filter_by(variant_id=variant_id, location_id=rack_id).one()
        reservation_db = db.query(models.StockReservation).one()

    assert wh_quant.quantity == 3  # reliquat après sortie client de 2
    assert rack_quant.quantity == 2  # retour recrédité sur l'emplacement ancré
    assert reservation_db.status == "returned"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import models
from scripts import reset_stock_to_zero


def _session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)
    return TestingSessionLocal, engine


def _seed_variant_with_quants(db):
    product = models.Product(
        reference_base="RST-PROD",
        name="Produit reset stock",
        material_type="ACCESSOIRE",
        unit="pce",
        supplier="MMG",
        product_type="stockable",
    )
    db.add(product)
    db.flush()
    variant = models.ProductVariant(
        product_id=product.id,
        reference="RST-PROD-001",
        quantity_in_stock=999,
        cost_price=10,
    )
    db.add(variant)
    db.flush()
    wh = models.StockLocation(name="WH/Stock", usage="internal", is_active=True)
    rack = models.StockLocation(name="WH/Rack-A", usage="internal", is_active=True)
    db.add_all([wh, rack])
    db.flush()
    db.add_all(
        [
            models.StockQuant(variant_id=variant.id, location_id=wh.id, quantity=5),
            models.StockQuant(variant_id=variant.id, location_id=rack.id, quantity=-2),
        ]
    )
    db.commit()
    return variant.id, wh.id, rack.id


def test_reset_stock_to_zero_dry_run_does_not_write(monkeypatch):
    TestingSessionLocal, engine = _session_factory()
    monkeypatch.setattr(reset_stock_to_zero, "SessionLocal", TestingSessionLocal)
    try:
        with TestingSessionLocal() as db:
            _seed_variant_with_quants(db)

        payload = reset_stock_to_zero.reset_stock_to_zero(
            apply=False,
            confirm=None,
            author="test",
            allow_active_reservations=False,
            reason="Test dry-run",
        )

        assert payload["plan"]["non_zero_quants"] == 2
        assert payload["result"]["created_moves"] == 0
        with TestingSessionLocal() as db:
            assert db.query(models.StockMove).count() == 0
            assert sorted(float(q.quantity) for q in db.query(models.StockQuant).all()) == [-2.0, 5.0]
    finally:
        models.Base.metadata.drop_all(bind=engine)


def test_reset_stock_to_zero_apply_creates_audited_moves_and_syncs_cache(monkeypatch):
    TestingSessionLocal, engine = _session_factory()
    monkeypatch.setattr(reset_stock_to_zero, "SessionLocal", TestingSessionLocal)
    try:
        with TestingSessionLocal() as db:
            variant_id, wh_id, rack_id = _seed_variant_with_quants(db)

        payload = reset_stock_to_zero.reset_stock_to_zero(
            apply=True,
            confirm=reset_stock_to_zero.CONFIRMATION,
            author="stock-admin",
            allow_active_reservations=False,
            reason="Mise en production inventaire",
        )

        assert payload["result"]["created_moves"] == 2
        assert payload["result"]["remaining_non_zero_quants"] == 0
        assert payload["result"]["remaining_cache_variants_non_zero"] == 0
        with TestingSessionLocal() as db:
            wh_quant = db.query(models.StockQuant).filter_by(variant_id=variant_id, location_id=wh_id).one()
            rack_quant = db.query(models.StockQuant).filter_by(variant_id=variant_id, location_id=rack_id).one()
            variant = db.query(models.ProductVariant).filter_by(id=variant_id).one()
            moves = db.query(models.StockMove).order_by(models.StockMove.id.asc()).all()
            assert float(wh_quant.quantity) == 0
            assert float(rack_quant.quantity) == 0
            assert float(variant.quantity_in_stock) == 0
            assert len(moves) == 2
            assert {move.document_type for move in moves} == {"stock_reset"}
            assert {move.source_screen for move in moves} == {"ops.reset_stock_to_zero"}
            assert all(move.business_reason == "Mise en production inventaire" for move in moves)
    finally:
        models.Base.metadata.drop_all(bind=engine)


def test_reset_stock_to_zero_apply_refuses_active_reservations(monkeypatch):
    TestingSessionLocal, engine = _session_factory()
    monkeypatch.setattr(reset_stock_to_zero, "SessionLocal", TestingSessionLocal)
    try:
        with TestingSessionLocal() as db:
            variant_id, _wh_id, _rack_id = _seed_variant_with_quants(db)
            reservation = models.StockReservation(reference="RSV-RESET-001", status="reserved")
            db.add(reservation)
            db.flush()
            db.add(
                models.StockReservationLine(
                    reservation_id=reservation.id,
                    variant_id=variant_id,
                    requested_quantity=1,
                    reserved_quantity=1,
                    status="reserved",
                )
            )
            db.commit()

        with pytest.raises(SystemExit):
            reset_stock_to_zero.reset_stock_to_zero(
                apply=True,
                confirm=reset_stock_to_zero.CONFIRMATION,
                author="stock-admin",
                allow_active_reservations=False,
                reason="Mise en production inventaire",
            )
        with TestingSessionLocal() as db:
            assert db.query(models.StockMove).count() == 0
    finally:
        models.Base.metadata.drop_all(bind=engine)

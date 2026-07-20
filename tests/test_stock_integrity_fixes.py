"""Tests des correctifs inventaire :

1. Export XLSX filtré sur les emplacements internes (document comptable).
2. Unicité des quants (variant_id, location_id) + création anti-course.
3. Ajustement POS via le moteur de stock (StockMove + quants) et fallback
   de disponibilité qui révèle les divergences au lieu de les masquer.
"""
import io
import logging

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import database, models
from backend.core import security
from backend.main import app
from backend.services.stock_reservations import physical_quantity_all_internal
from backend.services.stock_service import InventoryService


def _client_with_db(username: str = "stock-fix-tester"):
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
        db.add(models.User(username=username, pin_hash="test-pin", role="ADMIN", is_active=True))
        db.commit()
    token = security.create_access_token({"sub": username, "role": "ADMIN"})
    return TestClient(app), TestingSessionLocal, engine, {"Authorization": f"Bearer {token}"}


def _seed_variant(db, reference: str = "FIX-PROD-001", quantity_in_stock: float = 0.0):
    product = models.Product(
        reference_base=f"{reference}-BASE",
        name="Produit correctif stock",
        material_type="ACCESSOIRE",
        unit="pce",
        supplier="MMG",
        product_type="stockable",
        available_in_pos=True,
    )
    db.add(product)
    db.flush()
    variant = models.ProductVariant(
        product_id=product.id,
        reference=reference,
        cost_price=50,
        quantity_in_stock=quantity_in_stock,
        min_threshold=0,
    )
    db.add(variant)
    db.flush()
    return variant


# --- Correctif 1 : export inventaire filtré ---------------------------------

def test_export_inventory_only_contains_internal_locations():
    client, TestingSessionLocal, _engine, headers = _client_with_db("export-tester")
    try:
        with TestingSessionLocal() as db:
            variant = _seed_variant(db, reference="EXP-PROD-001")
            internal = models.StockLocation(name="WH/Stock", usage="internal", is_active=True)
            customer = models.StockLocation(name="Partner/Customer", usage="customer", is_active=True)
            inventory = models.StockLocation(name="Virtual/Inventory", usage="inventory", is_active=True)
            supplier = models.StockLocation(name="Partner/Supplier", usage="supplier", is_active=True)
            db.add_all([internal, customer, inventory, supplier])
            db.flush()
            # Stock réel : 10 ; vendu cumulé : 40 ; pertes : 5 ; en transit fournisseur : 7
            db.add_all([
                models.StockQuant(variant_id=variant.id, location_id=internal.id, quantity=10),
                models.StockQuant(variant_id=variant.id, location_id=customer.id, quantity=40),
                models.StockQuant(variant_id=variant.id, location_id=inventory.id, quantity=5),
                models.StockQuant(variant_id=variant.id, location_id=supplier.id, quantity=7),
            ])
            db.commit()

        response = client.get("/v2/stock/export/inventory", headers=headers)
        assert response.status_code == 200, response.text

        wb = openpyxl.load_workbook(io.BytesIO(response.content))
        ws = wb.active
        rows = [tuple(cell.value for cell in row) for row in ws.iter_rows(min_row=2)]

        # Une seule ligne : le quant interne. Les quants customer (ventes),
        # inventory (pertes) et supplier sont exclus de la valorisation.
        assert len(rows) == 1
        location_name, reference, _designation, _barcode, _ptype, qty, _unit, price, total = rows[0]
        assert location_name == "WH/Stock"
        assert reference == "EXP-PROD-001"
        assert float(qty) == 10
        assert float(total) == float(qty) * float(price)
    finally:
        app.dependency_overrides.pop(database.get_db, None)


# --- Correctif 2 : unicité + concurrence des quants --------------------------

def test_stock_quant_unique_constraint_exists_and_blocks_duplicates():
    _client, TestingSessionLocal, engine, _headers = _client_with_db("constraint-tester")
    try:
        # La contrainte est bien présente dans le schéma.
        uniques = inspect(engine).get_unique_constraints("stock_quants")
        assert any(
            list(u.get("column_names") or []) == ["variant_id", "location_id"]
            for u in uniques
        ), f"Contrainte d'unicité absente : {uniques}"

        with TestingSessionLocal() as db:
            variant = _seed_variant(db)
            location = models.StockLocation(name="WH/Uniq", usage="internal", is_active=True)
            db.add(location)
            db.flush()
            db.add(models.StockQuant(variant_id=variant.id, location_id=location.id, quantity=3))
            db.flush()

            # Un deuxième quant pour le même couple est rejeté (savepoint).
            db.add(models.StockQuant(variant_id=variant.id, location_id=location.id, quantity=9))
            with pytest.raises(IntegrityError):
                with db.begin_nested():
                    db.flush()
    finally:
        app.dependency_overrides.pop(database.get_db, None)


def test_get_or_create_quant_is_idempotent():
    _client, TestingSessionLocal, _engine, _headers = _client_with_db("idempotent-tester")
    try:
        with TestingSessionLocal() as db:
            variant = _seed_variant(db)
            location = models.StockLocation(name="WH/Idem", usage="internal", is_active=True)
            db.add(location)
            db.flush()

            first = InventoryService.get_or_create_quant(db, variant.id, location.id)
            second = InventoryService.get_or_create_quant(db, variant.id, location.id)
            assert first.id == second.id

            count = db.query(models.StockQuant).filter_by(variant_id=variant.id, location_id=location.id).count()
            assert count == 1
    finally:
        app.dependency_overrides.pop(database.get_db, None)


def test_get_or_create_quant_survives_concurrent_creation(tmp_path):
    """Course read-then-create simulée : un autre transaction insère le même
    quant entre le SELECT et le flush. Le savepoint + retry doit rattraper la
    ligne gagnante sans créer de doublon ni lever d'erreur."""
    db_path = tmp_path / "race.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    models.Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with SessionLocal() as db:
        variant = _seed_variant(db)
        location = models.StockLocation(name="WH/Race", usage="internal", is_active=True)
        db.add(location)
        db.flush()
        variant_id, location_id = variant.id, location.id
        db.commit()

    session = SessionLocal()
    inserted = {"done": False}

    def _concurrent_insert(conn, cursor, statement, parameters, context, executemany):
        # Simule la transaction concurrente gagnante : insertion sur une
        # connexion indépendante juste avant l'exécution de notre INSERT.
        if inserted["done"] or "INSERT INTO stock_quants" not in statement:
            return
        inserted["done"] = True
        with engine.begin() as conn2:
            conn2.execute(
                text(
                    "INSERT INTO stock_quants (variant_id, location_id, quantity) "
                    "VALUES (:v, :l, 7)"
                ),
                {"v": variant_id, "l": location_id},
            )

    event.listen(engine, "before_cursor_execute", _concurrent_insert)
    try:
        quant = InventoryService.get_or_create_quant(session, variant_id, location_id)
        session.commit()
        assert inserted["done"]  # la branche conflit a bien été exercée
        assert float(quant.quantity or 0) == 7  # ligne de la transaction concurrente
    finally:
        event.remove(engine, "before_cursor_execute", _concurrent_insert)
        session.close()

    with SessionLocal() as db:
        count = db.query(models.StockQuant).filter_by(variant_id=variant_id, location_id=location_id).count()
        assert count == 1
    engine.dispose()


def test_move_stock_locks_and_updates_quants_consistently():
    _client, TestingSessionLocal, _engine, _headers = _client_with_db("move-tester")
    try:
        with TestingSessionLocal() as db:
            variant = _seed_variant(db)
            source = models.StockLocation(name="WH/Src", usage="internal", is_active=True)
            dest = models.StockLocation(name="WH/Dst", usage="internal", is_active=True)
            db.add_all([source, dest])
            db.flush()
            db.add(models.StockQuant(variant_id=variant.id, location_id=source.id, quantity=8))
            db.flush()

            result = InventoryService.move_stock(
                db,
                variant_id=variant.id,
                source_location_id=source.id,
                dest_location_id=dest.id,
                quantity=3,
                reference="WH/TEST-LOCK",
            )
            assert result.previous_source_quantity == 8
            assert result.new_source_quantity == 5
            assert result.new_dest_quantity == 3

            source_quant = db.query(models.StockQuant).filter_by(variant_id=variant.id, location_id=source.id).one()
            dest_quant = db.query(models.StockQuant).filter_by(variant_id=variant.id, location_id=dest.id).one()
            assert float(source_quant.quantity) == 5
            assert float(dest_quant.quantity) == 3
            assert float(variant.quantity_in_stock) == 8
    finally:
        app.dependency_overrides.pop(database.get_db, None)


# --- Correctif 3 : ajustement POS + fallback --------------------------------

def test_pos_stock_adjustment_creates_move_and_updates_quants():
    client, TestingSessionLocal, _engine, headers = _client_with_db("pos-adjust-tester")
    try:
        with TestingSessionLocal() as db:
            variant = _seed_variant(db, reference="POS-ADJ-001")
            internal = models.StockLocation(name="WH/Stock", usage="internal", is_active=True)
            db.add(internal)
            db.flush()
            db.add(models.StockQuant(variant_id=variant.id, location_id=internal.id, quantity=10))
            db.commit()
            variant_id = variant.id

        # Ajustement à la baisse sans motif fourni par le frontend.
        response = client.put(f"/v2/pos/items/{variant_id}?stock=7", headers=headers)
        assert response.status_code == 200, response.text
        assert float(response.json()["stock"]) == 7

        with TestingSessionLocal() as db:
            move = (
                db.query(models.StockMove)
                .filter_by(variant_id=variant_id, source_screen="pos")
                .one()
            )
            assert float(move.quantity) == 3
            assert move.business_reason == "Ajustement manuel POS"
            assert move.document_type == "manual_inventory_adjustment"
            dest = db.query(models.StockLocation).filter_by(id=move.location_dest_id).one()
            assert dest.usage == "inventory"

            variant = db.query(models.ProductVariant).filter_by(id=variant_id).one()
            assert float(variant.quantity_in_stock) == 7

        # Ajustement à la hausse avec motif explicite.
        response = client.put(f"/v2/pos/items/{variant_id}?stock=12&reason=Erreur%20de%20comptage", headers=headers)
        assert response.status_code == 200, response.text

        with TestingSessionLocal() as db:
            move = (
                db.query(models.StockMove)
                .filter_by(variant_id=variant_id, source_screen="pos", business_reason="Erreur de comptage")
                .one()
            )
            assert float(move.quantity) == 5
            source = db.query(models.StockLocation).filter_by(id=move.location_id).one()
            assert source.usage == "inventory"
            internal_quant = (
                db.query(models.StockQuant)
                .join(models.StockLocation, models.StockQuant.location_id == models.StockLocation.id)
                .filter(models.StockQuant.variant_id == variant_id, models.StockLocation.usage == "internal")
                .one()
            )
            assert float(internal_quant.quantity) == 12
    finally:
        app.dependency_overrides.pop(database.get_db, None)


def test_pos_stock_adjustment_blocked_during_locked_inventory():
    client, TestingSessionLocal, _engine, headers = _client_with_db("pos-lock-tester")
    try:
        with TestingSessionLocal() as db:
            variant = _seed_variant(db, reference="POS-LOCK-001")
            internal = models.StockLocation(name="WH/Stock", usage="internal", is_active=True)
            db.add(internal)
            db.flush()
            db.add(models.StockQuant(variant_id=variant.id, location_id=internal.id, quantity=10))
            db.add(models.InventorySession(
                reference="INV-LOCK-001",
                name="Campagne gelée",
                status="counting",
                zone_locked=True,
                location_id=None,
            ))
            db.commit()
            variant_id = variant.id

        response = client.put(f"/v2/pos/items/{variant_id}?stock=7", headers=headers)
        assert response.status_code == 423, response.text
        assert "Zone gelée" in response.json()["detail"]

        with TestingSessionLocal() as db:
            assert db.query(models.StockMove).filter_by(variant_id=variant_id).count() == 0
    finally:
        app.dependency_overrides.pop(database.get_db, None)


def test_physical_quantity_fallback_reveals_divergence(caplog):
    _client, TestingSessionLocal, _engine, _headers = _client_with_db("fallback-tester")
    try:
        with TestingSessionLocal() as db:
            # Cache positif mais aucun quant : ancienne divergence masquée.
            variant = _seed_variant(db, reference="FALLBACK-001", quantity_in_stock=15)
            db.commit()

            # alembic fileConfig (test_schema_compatibility) désactive les
            # loggers existants dans le même process : on réactive le nôtre.
            logging.getLogger("backend.services.stock_reservations").disabled = False
            with caplog.at_level(logging.WARNING, logger="backend.services.stock_reservations"):
                physical = physical_quantity_all_internal(db, variant)

            # La somme des quants (source de vérité) fait foi : 0, pas le cache.
            assert physical == 0
            assert any("Divergence stock" in record.getMessage() for record in caplog.records)
    finally:
        app.dependency_overrides.pop(database.get_db, None)

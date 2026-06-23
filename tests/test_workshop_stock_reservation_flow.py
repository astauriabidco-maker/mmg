from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import database, models
from backend.core import security
from backend.main import app


def test_workshop_debit_reservation_is_consumed_only_when_confirmed():
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
        with TestingSessionLocal() as db:
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
                quantity_in_stock=5,
                min_threshold=0,
            )
            location = models.StockLocation(name="WH/Stock", usage="internal", is_active=True)
            db.add_all([variant, location])
            db.flush()
            db.add(models.StockQuant(variant_id=variant.id, location_id=location.id, quantity=5))
            db.commit()

        client = TestClient(app)
        token = security.create_access_token({"sub": "atelier-manager", "role": "ADMIN"})
        headers = {"Authorization": f"Bearer {token}"}
        content = b"SEPALUMIC GAMME BASE\r\nVER TEST\r\nRAL;7007;BAVETTE DE FAITAGE;3;barre  6,50\r\n"

        preview_response = client.post(
            "/v2/stock/workshop-debits/preview",
            headers=headers,
            files=[("files", ("SEPVER.TXT", content, "text/plain"))],
        )
        assert preview_response.status_code == 200, preview_response.text
        assert preview_response.json()["summary"]["stock_match_status"] == {"ok": 1}

        reserve_response = client.post(
            "/v2/stock/workshop-debits/reservations",
            headers=headers,
            data={"order_reference": "CMD-ATELIER-1"},
            files=[("files", ("SEPVER.TXT", content, "text/plain"))],
        )
        assert reserve_response.status_code == 200, reserve_response.text
        reservation = reserve_response.json()
        assert reservation["status"] == "reserved"
        assert reservation["lines"][0]["reserved_quantity"] == 3

        with TestingSessionLocal() as db:
            quant = db.query(models.StockQuant).one()
            variant = db.query(models.ProductVariant).one()
            assert quant.quantity == 5
            assert variant.quantity_in_stock == 5

        consume_response = client.post(
            f"/v2/stock/workshop-debits/reservations/{reservation['id']}/consume",
            headers=headers,
        )
        assert consume_response.status_code == 200, consume_response.text
        assert consume_response.json()["created_moves"] == 1

        with TestingSessionLocal() as db:
            source_quant = db.query(models.StockQuant).join(models.StockLocation).filter(models.StockLocation.name == "WH/Stock").one()
            dest_quant = (
                db.query(models.StockQuant)
                .join(models.StockLocation)
                .filter(models.StockLocation.name == "Production Ateliers")
                .one()
            )
            variant = db.query(models.ProductVariant).one()
            move = db.query(models.StockMove).one()
            reservation_db = db.query(models.StockReservation).one()

        assert source_quant.quantity == 2
        assert dest_quant.quantity == 3
        assert variant.quantity_in_stock == 2
        assert move.quantity == 3
        assert reservation_db.status == "consumed"
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)

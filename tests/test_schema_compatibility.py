from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from backend import models


def test_legacy_stock_and_delivery_schema_is_patched(tmp_path):
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE products (
                    id INTEGER PRIMARY KEY,
                    reference_base VARCHAR,
                    name VARCHAR,
                    material_type VARCHAR,
                    unit VARCHAR,
                    supplier VARCHAR,
                    product_type VARCHAR DEFAULT 'stockable',
                    available_in_pos BOOLEAN DEFAULT 0,
                    image_url VARCHAR
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE delivery_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reference VARCHAR UNIQUE,
                    route_id INTEGER,
                    order_id INTEGER,
                    client_name VARCHAR,
                    delivery_address VARCHAR,
                    contact_phone VARCHAR,
                    status VARCHAR,
                    signed_at DATETIME,
                    notes TEXT
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO products (
                    id, reference_base, name, material_type, unit
                ) VALUES (
                    1, 'P-001', 'Legacy product', 'PVC', 'pce'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO delivery_notes (
                    reference, order_id, client_name, status, notes
                ) VALUES (
                    'BL-LEGACY', 1, 'Client', 'READY', 'Ancienne note'
                )
                """
            )
        )

    models.ensure_schema_compatibility(engine)

    inspector = inspect(engine)
    product_columns = {column["name"] for column in inspector.get_columns("products")}
    delivery_columns = {column["name"] for column in inspector.get_columns("delivery_notes")}

    assert {"technical_doc_url", "compatible_series"}.issubset(product_columns)
    assert "delivery_notes" in delivery_columns

    Session = sessionmaker(bind=engine)
    with Session() as session:
        product = session.query(models.Product).one()
        note = session.query(models.DeliveryNote).one()

    assert product.technical_doc_url is None
    assert product.compatible_series is None
    assert note.delivery_notes == "Ancienne note"

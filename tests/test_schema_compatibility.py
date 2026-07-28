from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


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

    # La base legacy n'a pas de suivi Alembic : on la marque au dernier head
    # structurel, puis on cible la migration de rattrapage (e5c9f2a8d417) qui
    # rejoue les correctifs historiques d'ensure_schema_compatibility.
    alembic_cfg = Config("backend/alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.stamp(alembic_cfg, "d1f3a5b7c924")
    command.upgrade(alembic_cfg, "e5c9f2a8d417")

    inspector = inspect(engine)
    product_columns = {column["name"] for column in inspector.get_columns("products")}
    delivery_columns = {column["name"] for column in inspector.get_columns("delivery_notes")}

    assert {"technical_doc_url", "compatible_series", "catalog_status"}.issubset(product_columns)
    assert "delivery_notes" in delivery_columns
    assert "sale_order_id" in delivery_columns

    with engine.connect() as connection:
        product = connection.execute(
            text(
                "SELECT technical_doc_url, compatible_series, catalog_status "
                "FROM products"
            )
        ).one()
        note = connection.execute(
            text("SELECT delivery_notes FROM delivery_notes")
        ).one()

    assert product.technical_doc_url is None
    assert product.compatible_series is None
    assert product.catalog_status == "ACTIVE"
    assert note.delivery_notes == "Ancienne note"

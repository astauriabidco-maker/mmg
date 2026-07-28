from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_product_category_migration_preserves_legacy_classification(tmp_path):
    db_path = tmp_path / "product-category.db"
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
                    product_type VARCHAR
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO products (
                    id, reference_base, name, material_type, unit, product_type
                ) VALUES
                    (1, 'P-ALU', 'Profil existant', 'ALU', 'barre', 'stockable'),
                    (2, 'S-POSE', 'Pose', 'SERVICE', 'forfait', 'service')
                """
            )
        )

    alembic_cfg = Config("backend/alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.stamp(alembic_cfg, "c3f8a1d4e720")
    command.upgrade(alembic_cfg, "f6a2c4d8e901")

    columns = {column["name"] for column in inspect(engine).get_columns("products")}
    assert "category" in columns

    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT reference_base, category FROM products ORDER BY id")
        ).all()

    assert rows == [("P-ALU", "ALU"), ("S-POSE", "SERVICE")]

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_complete_inventory_migration_backfills_and_deduplicates(tmp_path):
    db_path = tmp_path / "inventory-controls.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE inventory_sessions (
                    id INTEGER PRIMARY KEY,
                    reference VARCHAR,
                    name VARCHAR,
                    status VARCHAR,
                    blind_counting BOOLEAN
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE inventory_count_lines (
                    id INTEGER PRIMARY KEY,
                    session_id INTEGER NOT NULL,
                    variant_id INTEGER NOT NULL,
                    location_id INTEGER NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO inventory_sessions (
                    id, reference, name, status, blind_counting
                ) VALUES (1, 'INV-LEGACY', 'Inventaire historique', 'draft', 0)
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO inventory_count_lines (
                    id, session_id, variant_id, location_id
                ) VALUES
                    (1, 1, 10, 20),
                    (2, 1, 10, 20)
                """
            )
        )

    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.stamp(config, "f1b2c3d4e5f6")
    command.upgrade(config, "a2c4e6f8b103")

    inspector = inspect(engine)
    session_columns = {
        column["name"] for column in inspector.get_columns("inventory_sessions")
    }
    assert {
        "inventory_type",
        "scheduled_for",
        "cycle_frequency_days",
        "assigned_usernames",
        "approval_threshold_value",
        "finance_approved_by",
        "finance_approved_at",
        "archived_by",
        "archived_at",
    }.issubset(session_columns)
    line_columns = {
        column["name"] for column in inspector.get_columns("inventory_count_lines")
    }
    assert {
        "version",
        "last_client_operation_id",
        "unit_cost_snapshot",
        "variance_value",
    }.issubset(line_columns)
    assert inspector.has_table("inventory_count_attachments")

    with engine.connect() as connection:
        session = connection.execute(
            text(
                """
                SELECT inventory_type, include_all_variants, assigned_usernames
                FROM inventory_sessions WHERE id = 1
                """
            )
        ).one()
        line_count = connection.execute(
            text("SELECT COUNT(*) FROM inventory_count_lines")
        ).scalar_one()
        version = connection.execute(
            text("SELECT version FROM inventory_count_lines WHERE id = 1")
        ).scalar_one()

    assert session == ("full", 0, "[]")
    assert line_count == 1
    assert version == 1

    unique_columns = {
        tuple(constraint["column_names"])
        for constraint in inspect(engine).get_unique_constraints(
            "inventory_count_lines"
        )
    }
    assert ("session_id", "variant_id", "location_id") in unique_columns
    assert ("last_client_operation_id",) in unique_columns

"""Add structured client sites and measure missions

Revision ID: b9e4c7a2d615
Revises: a7d2c4e9f631
Create Date: 2026-07-24 13:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b9e4c7a2d615"
down_revision: Union[str, Sequence[str], None] = "a7d2c4e9f631"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return _inspector().has_table(table_name)


def _columns(table_name: str) -> set[str]:
    if not _has_table(table_name):
        return set()
    return {column["name"] for column in _inspector().get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    if not _has_table(table_name):
        return set()
    return {index["name"] for index in _inspector().get_indexes(table_name)}


def upgrade() -> None:
    if "country" not in _columns("clients"):
        op.add_column(
            "clients",
            sa.Column("country", sa.String(), server_default="FR", nullable=True),
        )

    if not _has_table("client_site_addresses"):
        op.create_table(
            "client_site_addresses",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=False),
            sa.Column("label", sa.String(), server_default="Chantier", nullable=True),
            sa.Column("address_line1", sa.String(), nullable=False),
            sa.Column("address_line2", sa.String(), nullable=True),
            sa.Column("postal_code", sa.String(), nullable=True),
            sa.Column("city", sa.String(), nullable=True),
            sa.Column("country", sa.String(), server_default="FR", nullable=True),
            sa.Column("latitude", sa.Float(), nullable=True),
            sa.Column("longitude", sa.Float(), nullable=True),
            sa.Column("contact_name", sa.String(), nullable=True),
            sa.Column("contact_phone", sa.String(), nullable=True),
            sa.Column("access_instructions", sa.Text(), nullable=True),
            sa.Column("is_default", sa.Boolean(), server_default=sa.false(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(
                ["client_id"],
                ["clients.id"],
                name="fk_client_site_addresses_client_id_clients",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_client_site_addresses_client_id",
            "client_site_addresses",
            ["client_id"],
            unique=False,
        )
        op.create_index(
            "ix_client_site_addresses_id",
            "client_site_addresses",
            ["id"],
            unique=False,
        )

    if not _has_table("measure_missions"):
        op.create_table(
            "measure_missions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("reference", sa.String(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=False),
            sa.Column("site_address_id", sa.Integer(), nullable=True),
            sa.Column("sale_order_id", sa.Integer(), nullable=True),
            sa.Column("assigned_user_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(), server_default="DRAFT", nullable=False),
            sa.Column("purpose", sa.String(), nullable=True),
            sa.Column("scheduled_start", sa.DateTime(), nullable=True),
            sa.Column("scheduled_end", sa.DateTime(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(
                ["assigned_user_id"],
                ["users.id"],
                name="fk_measure_missions_assigned_user_id_users",
            ),
            sa.ForeignKeyConstraint(
                ["client_id"],
                ["clients.id"],
                name="fk_measure_missions_client_id_clients",
            ),
            sa.ForeignKeyConstraint(
                ["sale_order_id"],
                ["sale_orders.id"],
                name="fk_measure_missions_sale_order_id_sale_orders",
            ),
            sa.ForeignKeyConstraint(
                ["site_address_id"],
                ["client_site_addresses.id"],
                name="fk_measure_missions_site_address_id_client_sites",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("reference", name="uq_measure_missions_reference"),
        )
        for index_name, columns in (
            ("ix_measure_missions_id", ["id"]),
            ("ix_measure_missions_reference", ["reference"]),
            ("ix_measure_missions_client_id", ["client_id"]),
            ("ix_measure_missions_site_address_id", ["site_address_id"]),
            ("ix_measure_missions_sale_order_id", ["sale_order_id"]),
            ("ix_measure_missions_assigned_user_id", ["assigned_user_id"]),
            ("ix_measure_missions_status", ["status"]),
        ):
            op.create_index(index_name, "measure_missions", columns, unique=False)

    if not _has_table("measure_openings"):
        op.create_table(
            "measure_openings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("mission_id", sa.Integer(), nullable=False),
            sa.Column("sequence", sa.Integer(), server_default="1", nullable=False),
            sa.Column("label", sa.String(), nullable=False),
            sa.Column("room", sa.String(), nullable=True),
            sa.Column("product_type", sa.String(), server_default="WINDOW", nullable=True),
            sa.Column("width_mm", sa.Float(), nullable=True),
            sa.Column("height_mm", sa.Float(), nullable=True),
            sa.Column("passage_height_mm", sa.Float(), nullable=True),
            sa.Column("material", sa.String(), server_default="ALU", nullable=True),
            sa.Column("opening_type", sa.String(), nullable=True),
            sa.Column("opening_side", sa.String(), nullable=True),
            sa.Column("sash_count", sa.Integer(), server_default="1", nullable=True),
            sa.Column("installation_type", sa.String(), nullable=True),
            sa.Column("status", sa.String(), server_default="DRAFT", nullable=False),
            sa.Column("configuration", sa.JSON(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(
                ["mission_id"],
                ["measure_missions.id"],
                name="fk_measure_openings_mission_id_measure_missions",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "mission_id",
                "sequence",
                name="uq_measure_openings_mission_sequence",
            ),
        )
        op.create_index("ix_measure_openings_id", "measure_openings", ["id"], unique=False)
        op.create_index(
            "ix_measure_openings_mission_id",
            "measure_openings",
            ["mission_id"],
            unique=False,
        )
        op.create_index(
            "ix_measure_openings_status",
            "measure_openings",
            ["status"],
            unique=False,
        )

    mmg_columns = _columns("mmg_dossiers")
    if mmg_columns:
        with op.batch_alter_table("mmg_dossiers") as batch_op:
            if "client_id" not in mmg_columns:
                batch_op.add_column(sa.Column("client_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_mmg_dossiers_client_id_clients",
                    "clients",
                    ["client_id"],
                    ["id"],
                )
            if "site_address_id" not in mmg_columns:
                batch_op.add_column(sa.Column("site_address_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_mmg_dossiers_site_address_id_client_sites",
                    "client_site_addresses",
                    ["site_address_id"],
                    ["id"],
                )
            if "measure_mission_id" not in mmg_columns:
                batch_op.add_column(sa.Column("measure_mission_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_mmg_dossiers_measure_mission_id_measure_missions",
                    "measure_missions",
                    ["measure_mission_id"],
                    ["id"],
                )

        for index_name, columns, unique in (
            ("ix_mmg_dossiers_client_id", ["client_id"], False),
            ("ix_mmg_dossiers_site_address_id", ["site_address_id"], False),
            ("ix_mmg_dossiers_measure_mission_id", ["measure_mission_id"], False),
        ):
            if index_name not in _indexes("mmg_dossiers"):
                op.create_index(index_name, "mmg_dossiers", columns, unique=unique)


def downgrade() -> None:
    if _has_table("mmg_dossiers"):
        for index_name in (
            "ix_mmg_dossiers_measure_mission_id",
            "ix_mmg_dossiers_site_address_id",
            "ix_mmg_dossiers_client_id",
        ):
            if index_name in _indexes("mmg_dossiers"):
                op.drop_index(index_name, table_name="mmg_dossiers")
        mmg_columns = _columns("mmg_dossiers")
        with op.batch_alter_table("mmg_dossiers") as batch_op:
            for column_name in ("measure_mission_id", "site_address_id", "client_id"):
                if column_name in mmg_columns:
                    batch_op.drop_column(column_name)

    if _has_table("measure_openings"):
        op.drop_table("measure_openings")
    if _has_table("measure_missions"):
        op.drop_table("measure_missions")
    if _has_table("client_site_addresses"):
        op.drop_table("client_site_addresses")
    if "country" in _columns("clients"):
        op.drop_column("clients", "country")

"""Add workshop preparation notes

Revision ID: b2e6f8a1c407
Revises: a8d4e6f1b203
Create Date: 2026-07-24 20:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2e6f8a1c407"
down_revision: Union[str, Sequence[str], None] = "a8d4e6f1b203"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workshop_preparations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(), nullable=False),
        sa.Column("reservation_id", sa.Integer(), nullable=False),
        sa.Column("sale_order_id", sa.Integer(), nullable=True),
        sa.Column("production_order_id", sa.Integer(), nullable=True),
        sa.Column("source_location_id", sa.Integer(), nullable=False),
        sa.Column("destination_location_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("handed_over_by", sa.String(), nullable=True),
        sa.Column("handed_over_at", sa.DateTime(), nullable=True),
        sa.Column("returned_by", sa.String(), nullable=True),
        sa.Column("returned_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["destination_location_id"], ["stock_locations.id"]),
        sa.ForeignKeyConstraint(["production_order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["reservation_id"], ["stock_reservations.id"]),
        sa.ForeignKeyConstraint(["sale_order_id"], ["sale_orders.id"]),
        sa.ForeignKeyConstraint(["source_location_id"], ["stock_locations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference"),
        sa.UniqueConstraint("reservation_id"),
    )
    op.create_index("ix_workshop_preparations_id", "workshop_preparations", ["id"])
    op.create_index("ix_workshop_preparations_reference", "workshop_preparations", ["reference"])
    op.create_index("ix_workshop_preparations_reservation_id", "workshop_preparations", ["reservation_id"])
    op.create_index("ix_workshop_preparations_sale_order_id", "workshop_preparations", ["sale_order_id"])
    op.create_index("ix_workshop_preparations_production_order_id", "workshop_preparations", ["production_order_id"])
    op.create_index("ix_workshop_preparations_source_location_id", "workshop_preparations", ["source_location_id"])
    op.create_index("ix_workshop_preparations_destination_location_id", "workshop_preparations", ["destination_location_id"])
    op.create_index("ix_workshop_preparations_status", "workshop_preparations", ["status"])

    op.create_table(
        "workshop_preparation_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("preparation_id", sa.Integer(), nullable=False),
        sa.Column("reservation_line_id", sa.Integer(), nullable=False),
        sa.Column("variant_id", sa.Integer(), nullable=False),
        sa.Column("planned_quantity", sa.Float(), nullable=True),
        sa.Column("prepared_quantity", sa.Float(), nullable=True),
        sa.Column("transferred_quantity", sa.Float(), nullable=True),
        sa.Column("returned_quantity", sa.Float(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["preparation_id"], ["workshop_preparations.id"]),
        sa.ForeignKeyConstraint(["reservation_line_id"], ["stock_reservation_lines.id"]),
        sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workshop_preparation_lines_id", "workshop_preparation_lines", ["id"])
    op.create_index("ix_workshop_preparation_lines_preparation_id", "workshop_preparation_lines", ["preparation_id"])
    op.create_index("ix_workshop_preparation_lines_reservation_line_id", "workshop_preparation_lines", ["reservation_line_id"])
    op.create_index("ix_workshop_preparation_lines_variant_id", "workshop_preparation_lines", ["variant_id"])
    op.create_index("ix_workshop_preparation_lines_status", "workshop_preparation_lines", ["status"])


def downgrade() -> None:
    op.drop_index("ix_workshop_preparation_lines_status", table_name="workshop_preparation_lines")
    op.drop_index("ix_workshop_preparation_lines_variant_id", table_name="workshop_preparation_lines")
    op.drop_index("ix_workshop_preparation_lines_reservation_line_id", table_name="workshop_preparation_lines")
    op.drop_index("ix_workshop_preparation_lines_preparation_id", table_name="workshop_preparation_lines")
    op.drop_index("ix_workshop_preparation_lines_id", table_name="workshop_preparation_lines")
    op.drop_table("workshop_preparation_lines")
    op.drop_index("ix_workshop_preparations_status", table_name="workshop_preparations")
    op.drop_index("ix_workshop_preparations_destination_location_id", table_name="workshop_preparations")
    op.drop_index("ix_workshop_preparations_source_location_id", table_name="workshop_preparations")
    op.drop_index("ix_workshop_preparations_production_order_id", table_name="workshop_preparations")
    op.drop_index("ix_workshop_preparations_sale_order_id", table_name="workshop_preparations")
    op.drop_index("ix_workshop_preparations_reservation_id", table_name="workshop_preparations")
    op.drop_index("ix_workshop_preparations_reference", table_name="workshop_preparations")
    op.drop_index("ix_workshop_preparations_id", table_name="workshop_preparations")
    op.drop_table("workshop_preparations")

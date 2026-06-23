"""Add stock reservations

Revision ID: e4b9f21c8a77
Revises: d9a8c1f0b6e2
Create Date: 2026-06-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4b9f21c8a77"
down_revision: Union[str, Sequence[str], None] = "d9a8c1f0b6e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if not _has_table("stock_reservations"):
        op.create_table(
            "stock_reservations",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("reference", sa.String(), nullable=True),
            sa.Column("order_reference", sa.String(), nullable=True),
            sa.Column("project_reference", sa.String(), nullable=True),
            sa.Column("source_label", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("consumed_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_stock_reservations_id"), "stock_reservations", ["id"], unique=False)
        op.create_index(op.f("ix_stock_reservations_reference"), "stock_reservations", ["reference"], unique=True)
        op.create_index(op.f("ix_stock_reservations_order_reference"), "stock_reservations", ["order_reference"], unique=False)
        op.create_index(op.f("ix_stock_reservations_project_reference"), "stock_reservations", ["project_reference"], unique=False)
        op.create_index(op.f("ix_stock_reservations_status"), "stock_reservations", ["status"], unique=False)

    if not _has_table("stock_reservation_lines"):
        op.create_table(
            "stock_reservation_lines",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("reservation_id", sa.Integer(), nullable=True),
            sa.Column("variant_id", sa.Integer(), nullable=True),
            sa.Column("supplier", sa.String(), nullable=True),
            sa.Column("supplier_reference", sa.String(), nullable=True),
            sa.Column("designation", sa.String(), nullable=True),
            sa.Column("unit", sa.String(), nullable=True),
            sa.Column("requested_quantity", sa.Float(), nullable=True),
            sa.Column("reserved_quantity", sa.Float(), nullable=True),
            sa.Column("consumed_quantity", sa.Float(), nullable=True),
            sa.Column("available_at_reservation", sa.Float(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("source", sa.String(), nullable=True),
            sa.ForeignKeyConstraint(["reservation_id"], ["stock_reservations.id"]),
            sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_stock_reservation_lines_id"), "stock_reservation_lines", ["id"], unique=False)
        op.create_index(op.f("ix_stock_reservation_lines_status"), "stock_reservation_lines", ["status"], unique=False)


def downgrade() -> None:
    if _has_table("stock_reservation_lines"):
        op.drop_index(op.f("ix_stock_reservation_lines_status"), table_name="stock_reservation_lines")
        op.drop_index(op.f("ix_stock_reservation_lines_id"), table_name="stock_reservation_lines")
        op.drop_table("stock_reservation_lines")
    if _has_table("stock_reservations"):
        op.drop_index(op.f("ix_stock_reservations_status"), table_name="stock_reservations")
        op.drop_index(op.f("ix_stock_reservations_project_reference"), table_name="stock_reservations")
        op.drop_index(op.f("ix_stock_reservations_order_reference"), table_name="stock_reservations")
        op.drop_index(op.f("ix_stock_reservations_reference"), table_name="stock_reservations")
        op.drop_index(op.f("ix_stock_reservations_id"), table_name="stock_reservations")
        op.drop_table("stock_reservations")

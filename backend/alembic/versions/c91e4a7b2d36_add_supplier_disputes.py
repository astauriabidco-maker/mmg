"""Add supplier disputes

Revision ID: c91e4a7b2d36
Revises: 6a2d9f0b8c31
Create Date: 2026-07-23 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c91e4a7b2d36"
down_revision: Union[str, Sequence[str], None] = "6a2d9f0b8c31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if not _has_table("supplier_disputes"):
        op.create_table(
            "supplier_disputes",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("reference", sa.String(), nullable=True),
            sa.Column("supplier", sa.String(), nullable=True),
            sa.Column("purchase_order_id", sa.Integer(), nullable=True),
            sa.Column("supplier_invoice_id", sa.Integer(), nullable=True),
            sa.Column("title", sa.String(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("category", sa.String(), nullable=True),
            sa.Column("severity", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("created_by", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("closed_by", sa.String(), nullable=True),
            sa.Column("closed_at", sa.DateTime(), nullable=True),
            sa.Column("resolution_notes", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"]),
            sa.ForeignKeyConstraint(["supplier_invoice_id"], ["supplier_invoices.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_supplier_disputes_id"), "supplier_disputes", ["id"], unique=False)
        op.create_index(op.f("ix_supplier_disputes_reference"), "supplier_disputes", ["reference"], unique=True)
        op.create_index(op.f("ix_supplier_disputes_supplier"), "supplier_disputes", ["supplier"], unique=False)
        op.create_index(op.f("ix_supplier_disputes_purchase_order_id"), "supplier_disputes", ["purchase_order_id"], unique=False)
        op.create_index(op.f("ix_supplier_disputes_supplier_invoice_id"), "supplier_disputes", ["supplier_invoice_id"], unique=False)
        op.create_index(op.f("ix_supplier_disputes_status"), "supplier_disputes", ["status"], unique=False)


def downgrade() -> None:
    if _has_table("supplier_disputes"):
        op.drop_index(op.f("ix_supplier_disputes_status"), table_name="supplier_disputes")
        op.drop_index(op.f("ix_supplier_disputes_supplier_invoice_id"), table_name="supplier_disputes")
        op.drop_index(op.f("ix_supplier_disputes_purchase_order_id"), table_name="supplier_disputes")
        op.drop_index(op.f("ix_supplier_disputes_supplier"), table_name="supplier_disputes")
        op.drop_index(op.f("ix_supplier_disputes_reference"), table_name="supplier_disputes")
        op.drop_index(op.f("ix_supplier_disputes_id"), table_name="supplier_disputes")
        op.drop_table("supplier_disputes")

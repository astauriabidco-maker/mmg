"""Add supplier payments

Revision ID: f0d7c2a9e514
Revises: e1c7a9d4b820
Create Date: 2026-07-23 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f0d7c2a9e514"
down_revision: Union[str, Sequence[str], None] = "e1c7a9d4b820"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if not _has_table("supplier_payments"):
        op.create_table(
            "supplier_payments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("supplier_invoice_id", sa.Integer(), nullable=False),
            sa.Column("supplier", sa.String(), nullable=True),
            sa.Column("amount", sa.Numeric(14, 2), nullable=True),
            sa.Column("method", sa.String(), nullable=True),
            sa.Column("reference", sa.String(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("payment_date", sa.DateTime(), nullable=True),
            sa.Column("created_by", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["supplier_invoice_id"], ["supplier_invoices.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_supplier_payments_id"), "supplier_payments", ["id"], unique=False)
        op.create_index(op.f("ix_supplier_payments_supplier_invoice_id"), "supplier_payments", ["supplier_invoice_id"], unique=False)
        op.create_index(op.f("ix_supplier_payments_supplier"), "supplier_payments", ["supplier"], unique=False)


def downgrade() -> None:
    if _has_table("supplier_payments"):
        op.drop_index(op.f("ix_supplier_payments_supplier"), table_name="supplier_payments")
        op.drop_index(op.f("ix_supplier_payments_supplier_invoice_id"), table_name="supplier_payments")
        op.drop_index(op.f("ix_supplier_payments_id"), table_name="supplier_payments")
        op.drop_table("supplier_payments")

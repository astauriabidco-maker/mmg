"""add supplier invoice reconciliation

Revision ID: 0a4f9d2c8b31
Revises: f2b8c6d4a917
Create Date: 2026-07-16 16:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0a4f9d2c8b31"
down_revision: Union[str, Sequence[str], None] = "f2b8c6d4a917"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if not _has_table("supplier_invoices"):
        op.create_table(
            "supplier_invoices",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("reference", sa.String(), nullable=True),
            sa.Column("supplier_reference", sa.String(), nullable=True),
            sa.Column("purchase_order_id", sa.Integer(), nullable=True),
            sa.Column("supplier", sa.String(), nullable=True),
            sa.Column("issue_date", sa.DateTime(), nullable=True),
            sa.Column("due_date", sa.DateTime(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("subtotal", sa.Float(), nullable=True),
            sa.Column("discount_amount", sa.Float(), nullable=True),
            sa.Column("total_amount", sa.Float(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("author", sa.String(), nullable=True),
            sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_supplier_invoices_id"), "supplier_invoices", ["id"], unique=False)
        op.create_index(op.f("ix_supplier_invoices_purchase_order_id"), "supplier_invoices", ["purchase_order_id"], unique=False)
        op.create_index(op.f("ix_supplier_invoices_reference"), "supplier_invoices", ["reference"], unique=False)
        op.create_index(op.f("ix_supplier_invoices_status"), "supplier_invoices", ["status"], unique=False)

    if not _has_table("supplier_invoice_lines"):
        op.create_table(
            "supplier_invoice_lines",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("invoice_id", sa.Integer(), nullable=True),
            sa.Column("purchase_order_line_id", sa.Integer(), nullable=True),
            sa.Column("variant_id", sa.Integer(), nullable=True),
            sa.Column("description", sa.String(), nullable=True),
            sa.Column("quantity", sa.Float(), nullable=True),
            sa.Column("unit_price", sa.Float(), nullable=True),
            sa.Column("discount_percent", sa.Float(), nullable=True),
            sa.Column("line_total", sa.Float(), nullable=True),
            sa.ForeignKeyConstraint(["invoice_id"], ["supplier_invoices.id"]),
            sa.ForeignKeyConstraint(["purchase_order_line_id"], ["purchase_order_lines.id"]),
            sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_supplier_invoice_lines_id"), "supplier_invoice_lines", ["id"], unique=False)
        op.create_index(op.f("ix_supplier_invoice_lines_purchase_order_line_id"), "supplier_invoice_lines", ["purchase_order_line_id"], unique=False)


def downgrade() -> None:
    if _has_table("supplier_invoice_lines"):
        op.drop_index(op.f("ix_supplier_invoice_lines_purchase_order_line_id"), table_name="supplier_invoice_lines")
        op.drop_index(op.f("ix_supplier_invoice_lines_id"), table_name="supplier_invoice_lines")
        op.drop_table("supplier_invoice_lines")
    if _has_table("supplier_invoices"):
        op.drop_index(op.f("ix_supplier_invoices_status"), table_name="supplier_invoices")
        op.drop_index(op.f("ix_supplier_invoices_reference"), table_name="supplier_invoices")
        op.drop_index(op.f("ix_supplier_invoices_purchase_order_id"), table_name="supplier_invoices")
        op.drop_index(op.f("ix_supplier_invoices_id"), table_name="supplier_invoices")
        op.drop_table("supplier_invoices")

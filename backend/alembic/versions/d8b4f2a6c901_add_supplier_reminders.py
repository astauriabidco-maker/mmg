"""Add supplier reminders

Revision ID: d8b4f2a6c901
Revises: c91e4a7b2d36
Create Date: 2026-07-23 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8b4f2a6c901"
down_revision: Union[str, Sequence[str], None] = "c91e4a7b2d36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if not _has_table("supplier_reminders"):
        op.create_table(
            "supplier_reminders",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("purchase_order_id", sa.Integer(), nullable=False),
            sa.Column("supplier", sa.String(), nullable=True),
            sa.Column("channel", sa.String(), nullable=True),
            sa.Column("recipient", sa.String(), nullable=True),
            sa.Column("cc", sa.String(), nullable=True),
            sa.Column("subject", sa.String(), nullable=True),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("include_pdf", sa.Boolean(), nullable=True),
            sa.Column("sent_at", sa.DateTime(), nullable=True),
            sa.Column("created_by", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_supplier_reminders_id"), "supplier_reminders", ["id"], unique=False)
        op.create_index(op.f("ix_supplier_reminders_purchase_order_id"), "supplier_reminders", ["purchase_order_id"], unique=False)
        op.create_index(op.f("ix_supplier_reminders_supplier"), "supplier_reminders", ["supplier"], unique=False)
        op.create_index(op.f("ix_supplier_reminders_status"), "supplier_reminders", ["status"], unique=False)


def downgrade() -> None:
    if _has_table("supplier_reminders"):
        op.drop_index(op.f("ix_supplier_reminders_status"), table_name="supplier_reminders")
        op.drop_index(op.f("ix_supplier_reminders_supplier"), table_name="supplier_reminders")
        op.drop_index(op.f("ix_supplier_reminders_purchase_order_id"), table_name="supplier_reminders")
        op.drop_index(op.f("ix_supplier_reminders_id"), table_name="supplier_reminders")
        op.drop_table("supplier_reminders")

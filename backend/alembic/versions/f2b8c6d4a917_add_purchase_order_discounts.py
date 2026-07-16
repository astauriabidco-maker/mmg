"""add purchase order discounts

Revision ID: f2b8c6d4a917
Revises: e8a4c7d1f260
Create Date: 2026-07-16 14:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2b8c6d4a917"
down_revision: Union[str, Sequence[str], None] = "e8a4c7d1f260"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in sa.inspect(op.get_bind()).get_columns(table_name))


def upgrade() -> None:
    if _has_table("purchase_orders") and not _has_column("purchase_orders", "global_discount_percent"):
        op.add_column("purchase_orders", sa.Column("global_discount_percent", sa.Float(), nullable=True, server_default="0"))
        op.execute("UPDATE purchase_orders SET global_discount_percent = 0 WHERE global_discount_percent IS NULL")
    if _has_table("purchase_order_lines") and not _has_column("purchase_order_lines", "discount_percent"):
        op.add_column("purchase_order_lines", sa.Column("discount_percent", sa.Float(), nullable=True, server_default="0"))
        op.execute("UPDATE purchase_order_lines SET discount_percent = 0 WHERE discount_percent IS NULL")


def downgrade() -> None:
    if _has_table("purchase_order_lines") and _has_column("purchase_order_lines", "discount_percent"):
        op.drop_column("purchase_order_lines", "discount_percent")
    if _has_table("purchase_orders") and _has_column("purchase_orders", "global_discount_percent"):
        op.drop_column("purchase_orders", "global_discount_percent")

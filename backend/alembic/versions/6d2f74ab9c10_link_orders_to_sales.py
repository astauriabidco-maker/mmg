"""Link production orders to sale orders

Revision ID: 6d2f74ab9c10
Revises: a7c2d8e9f104
Create Date: 2026-06-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6d2f74ab9c10"
down_revision: Union[str, Sequence[str], None] = "a7c2d8e9f104"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _columns("orders")
    if "sale_order_id" not in columns:
        op.add_column("orders", sa.Column("sale_order_id", sa.Integer(), nullable=True))
        op.create_index(op.f("ix_orders_sale_order_id"), "orders", ["sale_order_id"], unique=False)
    if "sale_order_line_id" not in columns:
        op.add_column("orders", sa.Column("sale_order_line_id", sa.Integer(), nullable=True))
        op.create_index(op.f("ix_orders_sale_order_line_id"), "orders", ["sale_order_line_id"], unique=False)

    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_orders_sale_order_id_sale_orders",
            "orders",
            "sale_orders",
            ["sale_order_id"],
            ["id"],
        )
        op.create_foreign_key(
            "fk_orders_sale_order_line_id_sale_order_lines",
            "orders",
            "sale_order_lines",
            ["sale_order_line_id"],
            ["id"],
        )


def downgrade() -> None:
    columns = _columns("orders")
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_orders_sale_order_line_id_sale_order_lines", "orders", type_="foreignkey")
        op.drop_constraint("fk_orders_sale_order_id_sale_orders", "orders", type_="foreignkey")
    if "sale_order_line_id" in columns:
        op.drop_index(op.f("ix_orders_sale_order_line_id"), table_name="orders")
        op.drop_column("orders", "sale_order_line_id")
    if "sale_order_id" in columns:
        op.drop_index(op.f("ix_orders_sale_order_id"), table_name="orders")
        op.drop_column("orders", "sale_order_id")

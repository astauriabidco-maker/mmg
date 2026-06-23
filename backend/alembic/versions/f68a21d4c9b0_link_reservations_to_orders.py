"""Link reservations to sales and production orders

Revision ID: f68a21d4c9b0
Revises: e4b9f21c8a77
Create Date: 2026-06-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f68a21d4c9b0"
down_revision: Union[str, Sequence[str], None] = "e4b9f21c8a77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _columns("stock_reservations")
    if "sale_order_id" not in columns:
        op.add_column("stock_reservations", sa.Column("sale_order_id", sa.Integer(), nullable=True))
        op.create_index(op.f("ix_stock_reservations_sale_order_id"), "stock_reservations", ["sale_order_id"], unique=False)
    if "production_order_id" not in columns:
        op.add_column("stock_reservations", sa.Column("production_order_id", sa.Integer(), nullable=True))
        op.create_index(op.f("ix_stock_reservations_production_order_id"), "stock_reservations", ["production_order_id"], unique=False)

    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_stock_reservations_sale_order_id_sale_orders",
            "stock_reservations",
            "sale_orders",
            ["sale_order_id"],
            ["id"],
        )
        op.create_foreign_key(
            "fk_stock_reservations_production_order_id_orders",
            "stock_reservations",
            "orders",
            ["production_order_id"],
            ["id"],
        )


def downgrade() -> None:
    columns = _columns("stock_reservations")
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_stock_reservations_production_order_id_orders", "stock_reservations", type_="foreignkey")
        op.drop_constraint("fk_stock_reservations_sale_order_id_sale_orders", "stock_reservations", type_="foreignkey")
    if "production_order_id" in columns:
        op.drop_index(op.f("ix_stock_reservations_production_order_id"), table_name="stock_reservations")
        op.drop_column("stock_reservations", "production_order_id")
    if "sale_order_id" in columns:
        op.drop_index(op.f("ix_stock_reservations_sale_order_id"), table_name="stock_reservations")
        op.drop_column("stock_reservations", "sale_order_id")

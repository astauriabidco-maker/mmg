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


def _foreign_key_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {fk["name"] for fk in inspector.get_foreign_keys(table_name) if fk["name"]}


def upgrade() -> None:
    columns = _columns("stock_reservations")
    need_sale_order = "sale_order_id" not in columns
    need_production_order = "production_order_id" not in columns
    fk_names = _foreign_key_names("stock_reservations")
    need_fk_sale_order = "fk_stock_reservations_sale_order_id_sale_orders" not in fk_names
    need_fk_production_order = "fk_stock_reservations_production_order_id_orders" not in fk_names

    # batch_alter_table : recopie de table sur SQLite (pas d'ALTER de
    # contrainte), simples ALTER TABLE sur PostgreSQL.
    if need_sale_order or need_production_order or need_fk_sale_order or need_fk_production_order:
        with op.batch_alter_table("stock_reservations") as batch_op:
            if need_sale_order:
                batch_op.add_column(sa.Column("sale_order_id", sa.Integer(), nullable=True))
            if need_production_order:
                batch_op.add_column(sa.Column("production_order_id", sa.Integer(), nullable=True))
            if need_fk_sale_order:
                batch_op.create_foreign_key(
                    "fk_stock_reservations_sale_order_id_sale_orders",
                    "sale_orders",
                    ["sale_order_id"],
                    ["id"],
                )
            if need_fk_production_order:
                batch_op.create_foreign_key(
                    "fk_stock_reservations_production_order_id_orders",
                    "orders",
                    ["production_order_id"],
                    ["id"],
                )

    if need_sale_order:
        op.create_index(op.f("ix_stock_reservations_sale_order_id"), "stock_reservations", ["sale_order_id"], unique=False)
    if need_production_order:
        op.create_index(op.f("ix_stock_reservations_production_order_id"), "stock_reservations", ["production_order_id"], unique=False)


def downgrade() -> None:
    columns = _columns("stock_reservations")
    fk_names = _foreign_key_names("stock_reservations")

    with op.batch_alter_table("stock_reservations") as batch_op:
        if "fk_stock_reservations_production_order_id_orders" in fk_names:
            batch_op.drop_constraint("fk_stock_reservations_production_order_id_orders", type_="foreignkey")
        if "fk_stock_reservations_sale_order_id_sale_orders" in fk_names:
            batch_op.drop_constraint("fk_stock_reservations_sale_order_id_sale_orders", type_="foreignkey")
        if "production_order_id" in columns:
            batch_op.drop_column("production_order_id")
        if "sale_order_id" in columns:
            batch_op.drop_column("sale_order_id")

    if "production_order_id" in columns:
        op.drop_index(op.f("ix_stock_reservations_production_order_id"), table_name="stock_reservations")
    if "sale_order_id" in columns:
        op.drop_index(op.f("ix_stock_reservations_sale_order_id"), table_name="stock_reservations")

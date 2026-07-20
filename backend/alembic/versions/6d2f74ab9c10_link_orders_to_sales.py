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


def _foreign_key_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {fk["name"] for fk in inspector.get_foreign_keys(table_name) if fk["name"]}


def upgrade() -> None:
    columns = _columns("orders")
    need_sale_order = "sale_order_id" not in columns
    need_sale_order_line = "sale_order_line_id" not in columns
    fk_names = _foreign_key_names("orders")
    need_fk_sale_order = "fk_orders_sale_order_id_sale_orders" not in fk_names
    need_fk_sale_order_line = "fk_orders_sale_order_line_id_sale_order_lines" not in fk_names

    # batch_alter_table : recopie de table sur SQLite (pas d'ALTER de
    # contrainte), simples ALTER TABLE sur PostgreSQL.
    if need_sale_order or need_sale_order_line or need_fk_sale_order or need_fk_sale_order_line:
        with op.batch_alter_table("orders") as batch_op:
            if need_sale_order:
                batch_op.add_column(sa.Column("sale_order_id", sa.Integer(), nullable=True))
            if need_sale_order_line:
                batch_op.add_column(sa.Column("sale_order_line_id", sa.Integer(), nullable=True))
            if need_fk_sale_order:
                batch_op.create_foreign_key(
                    "fk_orders_sale_order_id_sale_orders",
                    "sale_orders",
                    ["sale_order_id"],
                    ["id"],
                )
            if need_fk_sale_order_line:
                batch_op.create_foreign_key(
                    "fk_orders_sale_order_line_id_sale_order_lines",
                    "sale_order_lines",
                    ["sale_order_line_id"],
                    ["id"],
                )

    if need_sale_order:
        op.create_index(op.f("ix_orders_sale_order_id"), "orders", ["sale_order_id"], unique=False)
    if need_sale_order_line:
        op.create_index(op.f("ix_orders_sale_order_line_id"), "orders", ["sale_order_line_id"], unique=False)


def downgrade() -> None:
    columns = _columns("orders")
    fk_names = _foreign_key_names("orders")

    with op.batch_alter_table("orders") as batch_op:
        if "fk_orders_sale_order_line_id_sale_order_lines" in fk_names:
            batch_op.drop_constraint("fk_orders_sale_order_line_id_sale_order_lines", type_="foreignkey")
        if "fk_orders_sale_order_id_sale_orders" in fk_names:
            batch_op.drop_constraint("fk_orders_sale_order_id_sale_orders", type_="foreignkey")
        if "sale_order_line_id" in columns:
            batch_op.drop_column("sale_order_line_id")
        if "sale_order_id" in columns:
            batch_op.drop_column("sale_order_id")

    if "sale_order_line_id" in columns:
        op.drop_index(op.f("ix_orders_sale_order_line_id"), table_name="orders")
    if "sale_order_id" in columns:
        op.drop_index(op.f("ix_orders_sale_order_id"), table_name="orders")

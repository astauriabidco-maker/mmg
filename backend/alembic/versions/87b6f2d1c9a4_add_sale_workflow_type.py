"""Add sale workflow type

Revision ID: 87b6f2d1c9a4
Revises: 6d2f74ab9c10
Create Date: 2026-06-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "87b6f2d1c9a4"
down_revision: Union[str, Sequence[str], None] = "6d2f74ab9c10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _columns("sale_orders")
    if "workflow_type" not in columns:
        op.add_column("sale_orders", sa.Column("workflow_type", sa.String(), nullable=True, server_default="FREE_SALE"))
        op.create_index(op.f("ix_sale_orders_workflow_type"), "sale_orders", ["workflow_type"], unique=False)
    op.execute("UPDATE sale_orders SET workflow_type = 'FREE_SALE' WHERE workflow_type IS NULL")


def downgrade() -> None:
    columns = _columns("sale_orders")
    if "workflow_type" in columns:
        op.drop_index(op.f("ix_sale_orders_workflow_type"), table_name="sale_orders")
        op.drop_column("sale_orders", "workflow_type")

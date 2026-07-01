"""Add sale order line type

Revision ID: 9f3b6c2d1a40
Revises: 87b6f2d1c9a4
Create Date: 2026-07-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9f3b6c2d1a40"
down_revision: Union[str, Sequence[str], None] = "87b6f2d1c9a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _columns("sale_order_lines")
    if "line_type" not in columns:
        op.add_column("sale_order_lines", sa.Column("line_type", sa.String(), nullable=True, server_default="SERVICE"))
        op.create_index(op.f("ix_sale_order_lines_line_type"), "sale_order_lines", ["line_type"], unique=False)
    op.execute(
        """
        UPDATE sale_order_lines
        SET line_type = CASE
            WHEN variant_id IS NOT NULL THEN 'STOCK_ITEM'
            ELSE 'SERVICE'
        END
        WHERE line_type IS NULL OR line_type = ''
        """
    )


def downgrade() -> None:
    columns = _columns("sale_order_lines")
    if "line_type" in columns:
        op.drop_index(op.f("ix_sale_order_lines_line_type"), table_name="sale_order_lines")
        op.drop_column("sale_order_lines", "line_type")

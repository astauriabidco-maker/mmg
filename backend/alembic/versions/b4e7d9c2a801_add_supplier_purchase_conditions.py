"""add supplier purchase conditions

Revision ID: b4e7d9c2a801
Revises: a3d9f2c8b601
Create Date: 2026-09-05 16:45:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4e7d9c2a801"
down_revision: Union[str, Sequence[str], None] = "a3d9f2c8b601"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in sa.inspect(op.get_bind()).get_columns(table_name))


def upgrade() -> None:
    if not _has_table("suppliers"):
        return

    columns = [
        ("minimum_order_amount", sa.Numeric(14, 2)),
        ("free_shipping_threshold", sa.Numeric(14, 2)),
        ("default_discount_percent", sa.Float(), "0"),
        ("price_valid_until", sa.DateTime()),
        ("preferred_families", sa.Text()),
    ]
    for item in columns:
        column_name, column_type, *server_default = item
        if not _has_column("suppliers", column_name):
            kwargs = {"server_default": server_default[0]} if server_default else {}
            op.add_column("suppliers", sa.Column(column_name, column_type, nullable=True, **kwargs))

    if _has_column("suppliers", "default_discount_percent"):
        op.execute("UPDATE suppliers SET default_discount_percent = 0 WHERE default_discount_percent IS NULL")


def downgrade() -> None:
    if not _has_table("suppliers"):
        return

    for column_name in [
        "preferred_families",
        "price_valid_until",
        "default_discount_percent",
        "free_shipping_threshold",
        "minimum_order_amount",
    ]:
        if _has_column("suppliers", column_name):
            op.drop_column("suppliers", column_name)

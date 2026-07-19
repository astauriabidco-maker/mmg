"""enhance supplier business profile

Revision ID: 7c9d1e4a5b28
Revises: 1b6e3f9a2c74
Create Date: 2026-07-17 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c9d1e4a5b28"
down_revision: Union[str, Sequence[str], None] = "1b6e3f9a2c74"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in sa.inspect(op.get_bind()).get_columns(table_name))


def upgrade() -> None:
    if not _has_table("suppliers"):
        return
    columns = {
        "supplier_status": sa.Column("supplier_status", sa.String(), nullable=True, server_default="ACTIVE"),
        "supplier_category": sa.Column("supplier_category", sa.String(), nullable=True),
        "default_currency": sa.Column("default_currency", sa.String(), nullable=True, server_default="EUR"),
        "incoterm": sa.Column("incoterm", sa.String(), nullable=True),
        "delivery_terms": sa.Column("delivery_terms", sa.String(), nullable=True),
    }
    for name, column in columns.items():
        if not _has_column("suppliers", name):
            op.add_column("suppliers", column)
    op.execute("UPDATE suppliers SET supplier_status = 'ACTIVE' WHERE supplier_status IS NULL OR supplier_status = ''")
    op.execute("UPDATE suppliers SET default_currency = 'EUR' WHERE default_currency IS NULL OR default_currency = ''")


def downgrade() -> None:
    if not _has_table("suppliers"):
        return
    for name in ["delivery_terms", "incoterm", "default_currency", "supplier_category", "supplier_status"]:
        if _has_column("suppliers", name):
            op.drop_column("suppliers", name)

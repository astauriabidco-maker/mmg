"""add supplier country

Revision ID: 1b6e3f9a2c74
Revises: 0a4f9d2c8b31
Create Date: 2026-07-16 18:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1b6e3f9a2c74"
down_revision: Union[str, Sequence[str], None] = "0a4f9d2c8b31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in sa.inspect(op.get_bind()).get_columns(table_name))


def upgrade() -> None:
    if _has_table("suppliers") and not _has_column("suppliers", "country"):
        op.add_column("suppliers", sa.Column("country", sa.String(), nullable=True))


def downgrade() -> None:
    if _has_table("suppliers") and _has_column("suppliers", "country"):
        op.drop_column("suppliers", "country")

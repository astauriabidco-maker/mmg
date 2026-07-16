"""add stock move audit metadata

Revision ID: d4c7b9a2e130
Revises: a9d8e7f6c5b4
Create Date: 2026-07-16 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4c7b9a2e130"
down_revision: Union[str, Sequence[str], None] = "a9d8e7f6c5b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return inspector.has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _has_table("stock_moves"):
        return
    for column_name in ["source_screen", "document_type", "document_reference", "business_reason"]:
        if not _has_column("stock_moves", column_name):
            op.add_column("stock_moves", sa.Column(column_name, sa.String(), nullable=True))


def downgrade() -> None:
    if not _has_table("stock_moves"):
        return
    for column_name in ["business_reason", "document_reference", "document_type", "source_screen"]:
        if _has_column("stock_moves", column_name):
            op.drop_column("stock_moves", column_name)

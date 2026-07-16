"""enhance supplier profile

Revision ID: e8a4c7d1f260
Revises: d4c7b9a2e130
Create Date: 2026-07-16 13:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8a4c7d1f260"
down_revision: Union[str, Sequence[str], None] = "d4c7b9a2e130"
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
    if not _has_table("suppliers"):
        return
    columns = [
        ("website", sa.String()),
        ("payment_terms", sa.String()),
        ("lead_time_days", sa.Integer()),
        ("preferred_contact_method", sa.String()),
        ("notes", sa.Text()),
    ]
    for column_name, column_type in columns:
        if not _has_column("suppliers", column_name):
            op.add_column("suppliers", sa.Column(column_name, column_type, nullable=True))


def downgrade() -> None:
    if not _has_table("suppliers"):
        return
    for column_name in ["notes", "preferred_contact_method", "lead_time_days", "payment_terms", "website"]:
        if _has_column("suppliers", column_name):
            op.drop_column("suppliers", column_name)

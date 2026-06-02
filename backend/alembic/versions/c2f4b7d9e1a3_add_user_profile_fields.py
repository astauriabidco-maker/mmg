"""Add user profile fields

Revision ID: c2f4b7d9e1a3
Revises: b8d3a6f4c921
Create Date: 2026-06-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c2f4b7d9e1a3"
down_revision: Union[str, Sequence[str], None] = "b8d3a6f4c921"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    """Upgrade schema."""
    user_columns = _columns("users")
    if not user_columns:
        return

    if "first_name" not in user_columns:
        op.add_column("users", sa.Column("first_name", sa.String(), nullable=True))
    if "last_name" not in user_columns:
        op.add_column("users", sa.Column("last_name", sa.String(), nullable=True))
    if "email" not in user_columns:
        op.add_column("users", sa.Column("email", sa.String(), nullable=True))
    if "phone" not in user_columns:
        op.add_column("users", sa.Column("phone", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    user_columns = _columns("users")
    for column_name in ("phone", "email", "last_name", "first_name"):
        if column_name in user_columns:
            op.drop_column("users", column_name)

"""add user secondary roles

Revision ID: 6a2d9f0b8c31
Revises: 4d8e2c7a9b15
Create Date: 2026-07-22 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6a2d9f0b8c31"
down_revision: Union[str, Sequence[str], None] = "4d8e2c7a9b15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if not _has_table("user_secondary_roles"):
        op.create_table(
            "user_secondary_roles",
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("role_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("user_id", "role_id"),
        )


def downgrade() -> None:
    if _has_table("user_secondary_roles"):
        op.drop_table("user_secondary_roles")

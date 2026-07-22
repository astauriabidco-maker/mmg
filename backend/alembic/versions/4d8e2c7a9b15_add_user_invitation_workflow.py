"""Add user invitation workflow

Revision ID: 4d8e2c7a9b15
Revises: e2f4b6a8c931
Create Date: 2026-07-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4d8e2c7a9b15"
down_revision: Union[str, Sequence[str], None] = "e2f4b6a8c931"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    user_columns = _columns("users")
    additions = [
        ("job_title", sa.Column("job_title", sa.String(), nullable=True)),
        ("team", sa.Column("team", sa.String(), nullable=True)),
        ("access_mode", sa.Column("access_mode", sa.String(), nullable=True, server_default="PIN")),
        ("invitation_status", sa.Column("invitation_status", sa.String(), nullable=True, server_default="ACTIVE")),
        ("invite_token", sa.Column("invite_token", sa.String(), nullable=True)),
        ("invited_at", sa.Column("invited_at", sa.DateTime(), nullable=True)),
        ("pin_must_change", sa.Column("pin_must_change", sa.Boolean(), nullable=True, server_default=sa.false())),
        ("last_login_at", sa.Column("last_login_at", sa.DateTime(), nullable=True)),
    ]
    for column_name, column in additions:
        if column_name not in user_columns:
            op.add_column("users", column)
    user_columns = _columns("users")
    if "invite_token" in user_columns:
        indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("users")}
        if "ix_users_invite_token" not in indexes:
            op.create_index("ix_users_invite_token", "users", ["invite_token"], unique=True)


def downgrade() -> None:
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("users")}
    if "ix_users_invite_token" in indexes:
        op.drop_index("ix_users_invite_token", table_name="users")
    user_columns = _columns("users")
    for column_name in (
        "last_login_at",
        "pin_must_change",
        "invited_at",
        "invite_token",
        "invitation_status",
        "access_mode",
        "team",
        "job_title",
    ):
        if column_name in user_columns:
            op.drop_column("users", column_name)

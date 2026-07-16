"""Enhance inventory count controls

Revision ID: a9d8e7f6c5b4
Revises: f3b2c1d4e5a6
Create Date: 2026-07-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a9d8e7f6c5b4"
down_revision: Union[str, Sequence[str], None] = "f3b2c1d4e5a6"
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
    """Upgrade schema."""
    if _has_table("inventory_sessions"):
        if not _has_column("inventory_sessions", "zone_locked"):
            op.add_column("inventory_sessions", sa.Column("zone_locked", sa.Boolean(), nullable=True, server_default=sa.true()))
        if not _has_column("inventory_sessions", "locked_at"):
            op.add_column("inventory_sessions", sa.Column("locked_at", sa.DateTime(), nullable=True))
        if not _has_column("inventory_sessions", "unlocked_at"):
            op.add_column("inventory_sessions", sa.Column("unlocked_at", sa.DateTime(), nullable=True))
        op.execute(
            "UPDATE inventory_sessions "
            "SET zone_locked = CASE WHEN status IN ('draft', 'counting') THEN TRUE ELSE FALSE END "
            "WHERE zone_locked IS NULL"
        )

    if _has_table("inventory_count_lines"):
        if not _has_column("inventory_count_lines", "status"):
            op.add_column("inventory_count_lines", sa.Column("status", sa.String(), nullable=True, server_default="ok"))
            op.create_index(op.f("ix_inventory_count_lines_status"), "inventory_count_lines", ["status"], unique=False)
            op.execute(
                "UPDATE inventory_count_lines "
                "SET status = CASE "
                "WHEN adjustment_move_id IS NOT NULL THEN 'validated' "
                "WHEN ABS(COALESCE(variance_quantity, 0)) <= 0.000001 THEN 'ok' "
                "ELSE 'variance' END "
                "WHERE status IS NULL OR status = 'ok'"
            )
        if not _has_column("inventory_count_lines", "recount_requested_by"):
            op.add_column("inventory_count_lines", sa.Column("recount_requested_by", sa.String(), nullable=True))
        if not _has_column("inventory_count_lines", "recount_requested_at"):
            op.add_column("inventory_count_lines", sa.Column("recount_requested_at", sa.DateTime(), nullable=True))
        if not _has_column("inventory_count_lines", "recount_notes"):
            op.add_column("inventory_count_lines", sa.Column("recount_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    if _has_table("inventory_count_lines"):
        if _has_column("inventory_count_lines", "recount_notes"):
            op.drop_column("inventory_count_lines", "recount_notes")
        if _has_column("inventory_count_lines", "recount_requested_at"):
            op.drop_column("inventory_count_lines", "recount_requested_at")
        if _has_column("inventory_count_lines", "recount_requested_by"):
            op.drop_column("inventory_count_lines", "recount_requested_by")
        if _has_column("inventory_count_lines", "status"):
            op.drop_index(op.f("ix_inventory_count_lines_status"), table_name="inventory_count_lines")
            op.drop_column("inventory_count_lines", "status")

    if _has_table("inventory_sessions"):
        if _has_column("inventory_sessions", "unlocked_at"):
            op.drop_column("inventory_sessions", "unlocked_at")
        if _has_column("inventory_sessions", "locked_at"):
            op.drop_column("inventory_sessions", "locked_at")
        if _has_column("inventory_sessions", "zone_locked"):
            op.drop_column("inventory_sessions", "zone_locked")

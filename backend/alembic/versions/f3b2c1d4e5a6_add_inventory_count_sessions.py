"""Add inventory count sessions

Revision ID: f3b2c1d4e5a6
Revises: c8f3a21d7b95
Create Date: 2026-07-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f3b2c1d4e5a6"
down_revision: Union[str, Sequence[str], None] = "c8f3a21d7b95"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return inspector.has_table(table_name)


def upgrade() -> None:
    """Upgrade schema."""
    if not _has_table("inventory_sessions"):
        op.create_table(
            "inventory_sessions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("reference", sa.String(), nullable=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("location_id", sa.Integer(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("validated_by", sa.String(), nullable=True),
            sa.Column("validated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["location_id"], ["stock_locations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("reference"),
        )
        op.create_index(op.f("ix_inventory_sessions_id"), "inventory_sessions", ["id"], unique=False)
        op.create_index(op.f("ix_inventory_sessions_location_id"), "inventory_sessions", ["location_id"], unique=False)
        op.create_index(op.f("ix_inventory_sessions_reference"), "inventory_sessions", ["reference"], unique=False)
        op.create_index(op.f("ix_inventory_sessions_status"), "inventory_sessions", ["status"], unique=False)

    if not _has_table("inventory_count_lines"):
        op.create_table(
            "inventory_count_lines",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("session_id", sa.Integer(), nullable=True),
            sa.Column("variant_id", sa.Integer(), nullable=True),
            sa.Column("location_id", sa.Integer(), nullable=True),
            sa.Column("expected_quantity", sa.Float(), nullable=True),
            sa.Column("counted_quantity", sa.Float(), nullable=True),
            sa.Column("variance_quantity", sa.Float(), nullable=True),
            sa.Column("reason", sa.String(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("counted_by", sa.String(), nullable=True),
            sa.Column("counted_at", sa.DateTime(), nullable=True),
            sa.Column("adjustment_move_id", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["adjustment_move_id"], ["stock_moves.id"]),
            sa.ForeignKeyConstraint(["location_id"], ["stock_locations.id"]),
            sa.ForeignKeyConstraint(["session_id"], ["inventory_sessions.id"]),
            sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_inventory_count_lines_id"), "inventory_count_lines", ["id"], unique=False)
        op.create_index(op.f("ix_inventory_count_lines_location_id"), "inventory_count_lines", ["location_id"], unique=False)
        op.create_index(op.f("ix_inventory_count_lines_session_id"), "inventory_count_lines", ["session_id"], unique=False)
        op.create_index(op.f("ix_inventory_count_lines_variant_id"), "inventory_count_lines", ["variant_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    if _has_table("inventory_count_lines"):
        op.drop_index(op.f("ix_inventory_count_lines_variant_id"), table_name="inventory_count_lines")
        op.drop_index(op.f("ix_inventory_count_lines_session_id"), table_name="inventory_count_lines")
        op.drop_index(op.f("ix_inventory_count_lines_location_id"), table_name="inventory_count_lines")
        op.drop_index(op.f("ix_inventory_count_lines_id"), table_name="inventory_count_lines")
        op.drop_table("inventory_count_lines")

    if _has_table("inventory_sessions"):
        op.drop_index(op.f("ix_inventory_sessions_status"), table_name="inventory_sessions")
        op.drop_index(op.f("ix_inventory_sessions_reference"), table_name="inventory_sessions")
        op.drop_index(op.f("ix_inventory_sessions_location_id"), table_name="inventory_sessions")
        op.drop_index(op.f("ix_inventory_sessions_id"), table_name="inventory_sessions")
        op.drop_table("inventory_sessions")

"""Complete inventory controls.

Revision ID: a2c4e6f8b103
Revises: f1b2c3d4e5f6
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a2c4e6f8b103"
down_revision: Union[str, Sequence[str], None] = "f1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _constraints(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(table_name)
        if constraint.get("name")
    }


def upgrade() -> None:
    session_columns = _columns("inventory_sessions")
    if session_columns:
        additions = [
            ("include_all_variants", sa.Column("include_all_variants", sa.Boolean(), nullable=True, server_default=sa.false())),
            ("inventory_type", sa.Column("inventory_type", sa.String(), nullable=True, server_default="full")),
            ("scheduled_for", sa.Column("scheduled_for", sa.DateTime(), nullable=True)),
            ("cycle_frequency_days", sa.Column("cycle_frequency_days", sa.Integer(), nullable=True)),
            ("assigned_usernames", sa.Column("assigned_usernames", sa.JSON(), nullable=True)),
            ("approval_threshold_value", sa.Column("approval_threshold_value", sa.Numeric(14, 2), nullable=True)),
            ("finance_approved_by", sa.Column("finance_approved_by", sa.String(), nullable=True)),
            ("finance_approved_at", sa.Column("finance_approved_at", sa.DateTime(), nullable=True)),
            ("archived_by", sa.Column("archived_by", sa.String(), nullable=True)),
            ("archived_at", sa.Column("archived_at", sa.DateTime(), nullable=True)),
        ]
        with op.batch_alter_table("inventory_sessions") as batch_op:
            for name, column in additions:
                if name not in session_columns:
                    batch_op.add_column(column)
        op.execute(
            "UPDATE inventory_sessions SET inventory_type = 'full' "
            "WHERE inventory_type IS NULL"
        )
        op.execute(
            "UPDATE inventory_sessions SET include_all_variants = FALSE "
            "WHERE include_all_variants IS NULL"
        )
        op.execute(
            "UPDATE inventory_sessions SET assigned_usernames = '[]' "
            "WHERE assigned_usernames IS NULL"
        )
        with op.batch_alter_table("inventory_sessions") as batch_op:
            batch_op.alter_column(
                "include_all_variants",
                existing_type=sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
            batch_op.alter_column(
                "inventory_type",
                existing_type=sa.String(),
                nullable=False,
                server_default="full",
            )
            batch_op.alter_column(
                "assigned_usernames",
                existing_type=sa.JSON(),
                nullable=False,
            )
            existing_indexes = {
                index["name"] for index in sa.inspect(op.get_bind()).get_indexes("inventory_sessions")
            }
            if "ix_inventory_sessions_inventory_type" not in existing_indexes:
                batch_op.create_index("ix_inventory_sessions_inventory_type", ["inventory_type"])
            if "ix_inventory_sessions_scheduled_for" not in existing_indexes:
                batch_op.create_index("ix_inventory_sessions_scheduled_for", ["scheduled_for"])
            if "ix_inventory_sessions_archived_at" not in existing_indexes:
                batch_op.create_index("ix_inventory_sessions_archived_at", ["archived_at"])

    line_columns = _columns("inventory_count_lines")
    if line_columns:
        additions = [
            ("version", sa.Column("version", sa.Integer(), nullable=True, server_default="1")),
            ("last_client_operation_id", sa.Column("last_client_operation_id", sa.String(), nullable=True)),
            ("unit_cost_snapshot", sa.Column("unit_cost_snapshot", sa.Numeric(14, 2), nullable=True)),
            ("variance_value", sa.Column("variance_value", sa.Numeric(14, 2), nullable=True)),
        ]
        with op.batch_alter_table("inventory_count_lines") as batch_op:
            for name, column in additions:
                if name not in line_columns:
                    batch_op.add_column(column)
        op.execute(
            "UPDATE inventory_count_lines SET version = 1 WHERE version IS NULL"
        )
        # Les anciennes bases peuvent contenir plusieurs lignes pour la même
        # référence/emplacement. On conserve la saisie la plus ancienne avant
        # d'installer la contrainte qui arbitre désormais les courses.
        op.execute(
            "DELETE FROM inventory_count_lines "
            "WHERE id NOT IN ("
            "SELECT MIN(id) FROM inventory_count_lines "
            "GROUP BY session_id, variant_id, location_id"
            ")"
        )
        with op.batch_alter_table("inventory_count_lines") as batch_op:
            batch_op.alter_column(
                "version",
                existing_type=sa.Integer(),
                nullable=False,
                server_default="1",
            )
            constraints = _constraints("inventory_count_lines")
            if "uq_inventory_count_line_session_variant_location" not in constraints:
                batch_op.create_unique_constraint(
                    "uq_inventory_count_line_session_variant_location",
                    ["session_id", "variant_id", "location_id"],
                )
            if "uq_inventory_count_lines_last_client_operation_id" not in constraints:
                batch_op.create_unique_constraint(
                    "uq_inventory_count_lines_last_client_operation_id",
                    ["last_client_operation_id"],
                )
            existing_indexes = {
                index["name"] for index in sa.inspect(op.get_bind()).get_indexes("inventory_count_lines")
            }
            if "ix_inventory_count_lines_last_client_operation_id" not in existing_indexes:
                batch_op.create_index(
                    "ix_inventory_count_lines_last_client_operation_id",
                    ["last_client_operation_id"],
                )

    if not _has_table("inventory_count_attachments"):
        op.create_table(
            "inventory_count_attachments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("line_id", sa.Integer(), nullable=False),
            sa.Column("filename", sa.String(), nullable=False),
            sa.Column("stored_filename", sa.String(), nullable=False),
            sa.Column("content_type", sa.String(), nullable=True),
            sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("uploaded_by", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["line_id"],
                ["inventory_count_lines.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_inventory_count_attachments_id",
            "inventory_count_attachments",
            ["id"],
        )
        op.create_index(
            "ix_inventory_count_attachments_line_id",
            "inventory_count_attachments",
            ["line_id"],
        )


def downgrade() -> None:
    if _has_table("inventory_count_attachments"):
        op.drop_index(
            "ix_inventory_count_attachments_line_id",
            table_name="inventory_count_attachments",
        )
        op.drop_index(
            "ix_inventory_count_attachments_id",
            table_name="inventory_count_attachments",
        )
        op.drop_table("inventory_count_attachments")

    if _has_table("inventory_count_lines"):
        with op.batch_alter_table("inventory_count_lines") as batch_op:
            batch_op.drop_index("ix_inventory_count_lines_last_client_operation_id")
            batch_op.drop_constraint(
                "uq_inventory_count_lines_last_client_operation_id",
                type_="unique",
            )
            batch_op.drop_constraint(
                "uq_inventory_count_line_session_variant_location",
                type_="unique",
            )
            batch_op.drop_column("variance_value")
            batch_op.drop_column("unit_cost_snapshot")
            batch_op.drop_column("last_client_operation_id")
            batch_op.drop_column("version")

    if _has_table("inventory_sessions"):
        with op.batch_alter_table("inventory_sessions") as batch_op:
            batch_op.drop_index("ix_inventory_sessions_archived_at")
            batch_op.drop_index("ix_inventory_sessions_scheduled_for")
            batch_op.drop_index("ix_inventory_sessions_inventory_type")
            batch_op.drop_column("archived_at")
            batch_op.drop_column("archived_by")
            batch_op.drop_column("finance_approved_at")
            batch_op.drop_column("finance_approved_by")
            batch_op.drop_column("approval_threshold_value")
            batch_op.drop_column("assigned_usernames")
            batch_op.drop_column("cycle_frequency_days")
            batch_op.drop_column("scheduled_for")
            batch_op.drop_column("inventory_type")
            batch_op.drop_column("include_all_variants")

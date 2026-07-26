"""add schedule execution

Revision ID: b4e7c1a9d203
Revises: a3f6c9e2b715
Create Date: 2026-07-26 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "b4e7c1a9d203"
down_revision = "a3f6c9e2b715"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("planning_notifications") as batch_op:
        batch_op.alter_column(
            "task_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch_op.add_column(
            sa.Column(
                "source_type",
                sa.String(),
                nullable=False,
                server_default="CALENDAR_TASK",
            )
        )
        batch_op.add_column(sa.Column("source_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            "ix_planning_notifications_source_type",
            ["source_type"],
            unique=False,
        )
        batch_op.create_index(
            "ix_planning_notifications_source_id",
            ["source_id"],
            unique=False,
        )

    op.execute(
        """
        UPDATE planning_notifications
        SET source_id = task_id
        WHERE source_id IS NULL
        """
    )

    op.create_table(
        "schedule_execution_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="TODO",
        ),
        sa.Column("assigned_user_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("active_since", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "elapsed_minutes",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_reason", sa.Text(), nullable=True),
        sa.Column("last_note", sa.Text(), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "updated_by_name",
            sa.String(),
            nullable=False,
            server_default="Système",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["assigned_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_type",
            "source_id",
            name="uq_schedule_execution_states_source",
        ),
    )
    for name, columns in (
        ("ix_schedule_execution_states_id", ["id"]),
        ("ix_schedule_execution_states_source_type", ["source_type"]),
        ("ix_schedule_execution_states_source_id", ["source_id"]),
        ("ix_schedule_execution_states_status", ["status"]),
        ("ix_schedule_execution_states_assigned_user_id", ["assigned_user_id"]),
        (
            "ix_schedule_execution_states_updated_by_user_id",
            ["updated_by_user_id"],
        ),
        (
            "ix_schedule_execution_states_status_assignee",
            ["status", "assigned_user_id"],
        ),
    ):
        op.create_index(name, "schedule_execution_states", columns, unique=False)

    op.create_table(
        "schedule_execution_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("state_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("previous_status", sa.String(), nullable=False),
        sa.Column("current_status", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "elapsed_minutes",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("responsible_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_name", sa.String(), nullable=False),
        sa.Column("source_screen", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["state_id"],
            ["schedule_execution_states.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["responsible_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_schedule_execution_logs_id", ["id"]),
        ("ix_schedule_execution_logs_state_id", ["state_id"]),
        ("ix_schedule_execution_logs_action", ["action"]),
        (
            "ix_schedule_execution_logs_responsible_user_id",
            ["responsible_user_id"],
        ),
        ("ix_schedule_execution_logs_actor_user_id", ["actor_user_id"]),
        ("ix_schedule_execution_logs_created_at", ["created_at"]),
        (
            "ix_schedule_execution_logs_state_created",
            ["state_id", "created_at"],
        ),
    ):
        op.create_index(name, "schedule_execution_logs", columns, unique=False)


def downgrade():
    op.drop_table("schedule_execution_logs")
    op.drop_table("schedule_execution_states")
    with op.batch_alter_table("planning_notifications") as batch_op:
        batch_op.drop_index("ix_planning_notifications_source_id")
        batch_op.drop_index("ix_planning_notifications_source_type")
        batch_op.drop_column("source_id")
        batch_op.drop_column("source_type")
        batch_op.alter_column(
            "task_id",
            existing_type=sa.Integer(),
            nullable=False,
        )

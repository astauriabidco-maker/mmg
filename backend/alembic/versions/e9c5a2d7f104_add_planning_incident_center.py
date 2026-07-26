"""add planning incident center

Revision ID: e9c5a2d7f104
Revises: d8b4f1a2c603
Create Date: 2026-07-26 23:35:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "e9c5a2d7f104"
down_revision = "d8b4f1a2c603"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "planning_alert_rules",
        sa.Column("severity", sa.String(), nullable=False, server_default="MEDIUM"),
    )
    op.add_column(
        "planning_alert_rules",
        sa.Column("escalation_minutes", sa.Integer(), nullable=False, server_default="30"),
    )
    op.add_column(
        "planning_alert_rules",
        sa.Column("notify_pwa", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "planning_alert_rules",
        sa.Column("notify_email", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.execute(
        "UPDATE planning_alert_rules SET severity = 'CRITICAL', "
        "escalation_minutes = 15 WHERE code = 'BLOCKED'"
    )
    op.execute(
        "UPDATE planning_alert_rules SET severity = 'MEDIUM', "
        "escalation_minutes = 30 WHERE code = 'PAUSE_TOO_LONG'"
    )
    op.execute(
        "UPDATE planning_alert_rules SET severity = 'HIGH', "
        "escalation_minutes = 30 WHERE code = 'DURATION_OVERRUN'"
    )

    op.create_table(
        "planning_incidents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(), nullable=False),
        sa.Column("incident_key", sa.String(), nullable=False),
        sa.Column("alert_code", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False, server_default="MEDIUM"),
        sa.Column("status", sa.String(), nullable=False, server_default="OPEN"),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("execution_state_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("responsible_user_id", sa.Integer(), nullable=True),
        sa.Column("assigned_manager_user_id", sa.Integer(), nullable=True),
        sa.Column("triggered_at", sa.DateTime(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        sa.Column("acknowledged_by_user_id", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("escalation_level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("escalated_at", sa.DateTime(), nullable=True),
        sa.Column("next_escalation_at", sa.DateTime(), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["execution_state_id"],
            ["schedule_execution_states.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["task_id"], ["calendar_tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["responsible_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_manager_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["acknowledged_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference"),
        sa.UniqueConstraint("incident_key"),
    )
    for column in (
        "id",
        "reference",
        "incident_key",
        "alert_code",
        "severity",
        "status",
        "source_type",
        "source_id",
        "execution_state_id",
        "task_id",
        "responsible_user_id",
        "assigned_manager_user_id",
        "triggered_at",
        "next_escalation_at",
    ):
        op.create_index(
            op.f(f"ix_planning_incidents_{column}"),
            "planning_incidents",
            [column],
            unique=column in {"reference", "incident_key"},
        )
    op.create_index(
        "ix_planning_incidents_status_severity_triggered",
        "planning_incidents",
        ["status", "severity", "triggered_at"],
    )
    op.create_index(
        "ix_planning_incidents_source",
        "planning_incidents",
        ["source_type", "source_id"],
    )

    op.create_table(
        "planning_incident_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("previous_status", sa.String(), nullable=True),
        sa.Column("current_status", sa.String(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_name", sa.String(), nullable=False, server_default="Système"),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("changes", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["planning_incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("id", "incident_id", "action", "actor_user_id", "created_at"):
        op.create_index(
            op.f(f"ix_planning_incident_history_{column}"),
            "planning_incident_history",
            [column],
        )
    op.create_index(
        "ix_planning_incident_history_incident_created",
        "planning_incident_history",
        ["incident_id", "created_at"],
    )

    with op.batch_alter_table("planning_notifications") as batch_op:
        batch_op.add_column(sa.Column("incident_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_planning_notifications_incident_id",
            "planning_incidents",
            ["incident_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            op.f("ix_planning_notifications_incident_id"),
            ["incident_id"],
        )


def downgrade():
    with op.batch_alter_table("planning_notifications") as batch_op:
        batch_op.drop_index(op.f("ix_planning_notifications_incident_id"))
        batch_op.drop_constraint(
            "fk_planning_notifications_incident_id",
            type_="foreignkey",
        )
        batch_op.drop_column("incident_id")
    op.drop_index(
        "ix_planning_incident_history_incident_created",
        table_name="planning_incident_history",
    )
    for column in ("created_at", "actor_user_id", "action", "incident_id", "id"):
        op.drop_index(
            op.f(f"ix_planning_incident_history_{column}"),
            table_name="planning_incident_history",
        )
    op.drop_table("planning_incident_history")
    op.drop_index("ix_planning_incidents_source", table_name="planning_incidents")
    op.drop_index(
        "ix_planning_incidents_status_severity_triggered",
        table_name="planning_incidents",
    )
    for column in (
        "next_escalation_at",
        "triggered_at",
        "assigned_manager_user_id",
        "responsible_user_id",
        "task_id",
        "execution_state_id",
        "source_id",
        "source_type",
        "status",
        "severity",
        "alert_code",
        "incident_key",
        "reference",
        "id",
    ):
        op.drop_index(
            op.f(f"ix_planning_incidents_{column}"),
            table_name="planning_incidents",
        )
    op.drop_table("planning_incidents")
    op.drop_column("planning_alert_rules", "notify_email")
    op.drop_column("planning_alert_rules", "notify_pwa")
    op.drop_column("planning_alert_rules", "escalation_minutes")
    op.drop_column("planning_alert_rules", "severity")

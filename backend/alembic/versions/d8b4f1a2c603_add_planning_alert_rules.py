"""add planning alert rules

Revision ID: d8b4f1a2c603
Revises: c7a2e9d4f601
Create Date: 2026-07-26 22:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "d8b4f1a2c603"
down_revision = "c7a2e9d4f601"
branch_labels = None
depends_on = None


DEFAULT_RULES = (
    (
        "BLOCKED",
        "Tâche bloquée",
        "Alerte immédiate lorsqu’une tâche est déclarée bloquée.",
        0,
        "BOTH",
    ),
    (
        "PAUSE_TOO_LONG",
        "Pause prolongée",
        "Alerte lorsqu’une tâche reste en pause au-delà du seuil.",
        30,
        "BOTH",
    ),
    (
        "DURATION_OVERRUN",
        "Durée prévue dépassée",
        "Alerte lorsque le temps d’exécution dépasse la durée planifiée.",
        15,
        "BOTH",
    ),
)


def upgrade():
    table = op.create_table(
        "planning_alert_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "threshold_minutes",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "recipient_mode",
            sa.String(),
            nullable=False,
            server_default="BOTH",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(
        op.f("ix_planning_alert_rules_id"),
        "planning_alert_rules",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_planning_alert_rules_code"),
        "planning_alert_rules",
        ["code"],
        unique=True,
    )
    op.create_index(
        op.f("ix_planning_alert_rules_is_active"),
        "planning_alert_rules",
        ["is_active"],
        unique=False,
    )
    op.bulk_insert(
        table,
        [
            {
                "code": code,
                "label": label,
                "description": description,
                "threshold_minutes": threshold,
                "recipient_mode": recipient_mode,
                "is_active": True,
            }
            for code, label, description, threshold, recipient_mode
            in DEFAULT_RULES
        ],
    )


def downgrade():
    op.drop_index(
        op.f("ix_planning_alert_rules_is_active"),
        table_name="planning_alert_rules",
    )
    op.drop_index(
        op.f("ix_planning_alert_rules_code"),
        table_name="planning_alert_rules",
    )
    op.drop_index(
        op.f("ix_planning_alert_rules_id"),
        table_name="planning_alert_rules",
    )
    op.drop_table("planning_alert_rules")

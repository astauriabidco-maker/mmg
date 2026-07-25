"""Add semi-automatic CRM reminder planning.

Revision ID: c4f8a1d7e295
Revises: b1e7c4d9a632
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4f8a1d7e295"
down_revision: Union[str, None] = "b1e7c4d9a632"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "crm_opportunities",
        sa.Column(
            "stage_entered_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_crm_opportunities_stage_entered_at",
        "crm_opportunities",
        ["stage_entered_at"],
        unique=False,
    )

    op.create_table(
        "crm_reminder_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("delay_days", sa.Integer(), server_default="2", nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column(
            "assignment_strategy",
            sa.String(),
            server_default="OPPORTUNITY_OWNER",
            nullable=False,
        ),
        sa.Column("fixed_user_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by", sa.String(), server_default="Système", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["fixed_user_id"],
            ["users.id"],
            name="fk_crm_reminder_rules_fixed_user",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["crm_reminder_templates.id"],
            name="fk_crm_reminder_rules_template",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stage", name="uq_crm_reminder_rules_stage"),
    )
    for name, columns, unique in (
        ("ix_crm_reminder_rules_id", ["id"], False),
        ("ix_crm_reminder_rules_stage", ["stage"], True),
        ("ix_crm_reminder_rules_template_id", ["template_id"], False),
        ("ix_crm_reminder_rules_assignment_strategy", ["assignment_strategy"], False),
        ("ix_crm_reminder_rules_fixed_user_id", ["fixed_user_id"], False),
        ("ix_crm_reminder_rules_is_active", ["is_active"], False),
    ):
        op.create_index(name, "crm_reminder_rules", columns, unique=unique)

    op.create_table(
        "crm_reminder_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_key", sa.String(), nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("assigned_user_id", sa.Integer(), nullable=True),
        sa.Column("sent_delivery_id", sa.Integer(), nullable=True),
        sa.Column("stage_snapshot", sa.String(), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(), server_default="PENDING", nullable=False),
        sa.Column("cancelled_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(), server_default="Système", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assigned_user_id"],
            ["users.id"],
            name="fk_crm_reminder_plans_assigned_user",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["clients.id"],
            name="fk_crm_reminder_plans_client",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["crm_opportunities.id"],
            name="fk_crm_reminder_plans_opportunity",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["crm_reminder_rules.id"],
            name="fk_crm_reminder_plans_rule",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sent_delivery_id"],
            ["crm_reminder_deliveries.id"],
            name="fk_crm_reminder_plans_delivery",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_key", name="uq_crm_reminder_plans_plan_key"),
    )
    for name, columns, unique in (
        ("ix_crm_reminder_plans_id", ["id"], False),
        ("ix_crm_reminder_plans_plan_key", ["plan_key"], True),
        ("ix_crm_reminder_plans_rule_id", ["rule_id"], False),
        ("ix_crm_reminder_plans_opportunity_id", ["opportunity_id"], False),
        ("ix_crm_reminder_plans_client_id", ["client_id"], False),
        ("ix_crm_reminder_plans_assigned_user_id", ["assigned_user_id"], False),
        ("ix_crm_reminder_plans_sent_delivery_id", ["sent_delivery_id"], False),
        ("ix_crm_reminder_plans_stage_snapshot", ["stage_snapshot"], False),
        ("ix_crm_reminder_plans_due_at", ["due_at"], False),
        ("ix_crm_reminder_plans_status", ["status"], False),
    ):
        op.create_index(name, "crm_reminder_plans", columns, unique=unique)


def downgrade() -> None:
    for name in (
        "ix_crm_reminder_plans_status",
        "ix_crm_reminder_plans_due_at",
        "ix_crm_reminder_plans_stage_snapshot",
        "ix_crm_reminder_plans_sent_delivery_id",
        "ix_crm_reminder_plans_assigned_user_id",
        "ix_crm_reminder_plans_client_id",
        "ix_crm_reminder_plans_opportunity_id",
        "ix_crm_reminder_plans_rule_id",
        "ix_crm_reminder_plans_plan_key",
        "ix_crm_reminder_plans_id",
    ):
        op.drop_index(name, table_name="crm_reminder_plans")
    op.drop_table("crm_reminder_plans")

    for name in (
        "ix_crm_reminder_rules_is_active",
        "ix_crm_reminder_rules_fixed_user_id",
        "ix_crm_reminder_rules_assignment_strategy",
        "ix_crm_reminder_rules_template_id",
        "ix_crm_reminder_rules_stage",
        "ix_crm_reminder_rules_id",
    ):
        op.drop_index(name, table_name="crm_reminder_rules")
    op.drop_table("crm_reminder_rules")

    op.drop_index(
        "ix_crm_opportunities_stage_entered_at",
        table_name="crm_opportunities",
    )
    op.drop_column("crm_opportunities", "stage_entered_at")

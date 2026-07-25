"""Add controlled CRM reminder templates and delivery history.

Revision ID: b1e7c4d9a632
Revises: a9d4e7f2c631
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1e7c4d9a632"
down_revision: Union[str, None] = "a9d4e7f2c631"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crm_reminder_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("subject_template", sa.String(), nullable=False),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by", sa.String(), server_default="Système", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_crm_reminder_templates_code"),
    )
    op.create_index(
        "ix_crm_reminder_templates_id",
        "crm_reminder_templates",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_crm_reminder_templates_code",
        "crm_reminder_templates",
        ["code"],
        unique=True,
    )
    op.create_index(
        "ix_crm_reminder_templates_is_active",
        "crm_reminder_templates",
        ["is_active"],
        unique=False,
    )

    op.create_table(
        "crm_reminder_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reminder_key", sa.String(), nullable=True),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=True),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("activity_id", sa.Integer(), nullable=True),
        sa.Column("recipient", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), server_default="PREPARED", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(), server_default="Système", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["crm_activities.id"],
            name="fk_crm_reminder_deliveries_activity",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["clients.id"],
            name="fk_crm_reminder_deliveries_client",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["crm_opportunities.id"],
            name="fk_crm_reminder_deliveries_opportunity",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["crm_reminder_templates.id"],
            name="fk_crm_reminder_deliveries_template",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_crm_reminder_deliveries_id", ["id"]),
        ("ix_crm_reminder_deliveries_reminder_key", ["reminder_key"]),
        ("ix_crm_reminder_deliveries_client_id", ["client_id"]),
        ("ix_crm_reminder_deliveries_opportunity_id", ["opportunity_id"]),
        ("ix_crm_reminder_deliveries_template_id", ["template_id"]),
        ("ix_crm_reminder_deliveries_activity_id", ["activity_id"]),
        ("ix_crm_reminder_deliveries_status", ["status"]),
    ):
        op.create_index(name, "crm_reminder_deliveries", columns, unique=False)


def downgrade() -> None:
    for name in (
        "ix_crm_reminder_deliveries_status",
        "ix_crm_reminder_deliveries_activity_id",
        "ix_crm_reminder_deliveries_template_id",
        "ix_crm_reminder_deliveries_opportunity_id",
        "ix_crm_reminder_deliveries_client_id",
        "ix_crm_reminder_deliveries_reminder_key",
        "ix_crm_reminder_deliveries_id",
    ):
        op.drop_index(name, table_name="crm_reminder_deliveries")
    op.drop_table("crm_reminder_deliveries")

    op.drop_index(
        "ix_crm_reminder_templates_is_active",
        table_name="crm_reminder_templates",
    )
    op.drop_index(
        "ix_crm_reminder_templates_code",
        table_name="crm_reminder_templates",
    )
    op.drop_index(
        "ix_crm_reminder_templates_id",
        table_name="crm_reminder_templates",
    )
    op.drop_table("crm_reminder_templates")

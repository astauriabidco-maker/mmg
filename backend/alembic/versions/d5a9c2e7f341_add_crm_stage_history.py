"""add crm opportunity stage history

Revision ID: d5a9c2e7f341
Revises: c4f8a1d7e295
Create Date: 2026-07-25 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "d5a9c2e7f341"
down_revision = "c4f8a1d7e295"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "crm_opportunity_stage_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("from_stage", sa.String(), nullable=True),
        sa.Column("to_stage", sa.String(), nullable=False),
        sa.Column("changed_by", sa.String(), nullable=False),
        sa.Column("changed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["crm_opportunities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_crm_opportunity_stage_history_id"),
        "crm_opportunity_stage_history",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crm_opportunity_stage_history_opportunity_id"),
        "crm_opportunity_stage_history",
        ["opportunity_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crm_opportunity_stage_history_from_stage"),
        "crm_opportunity_stage_history",
        ["from_stage"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crm_opportunity_stage_history_to_stage"),
        "crm_opportunity_stage_history",
        ["to_stage"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crm_opportunity_stage_history_changed_at"),
        "crm_opportunity_stage_history",
        ["changed_at"],
        unique=False,
    )
    op.execute(
        """
        INSERT INTO crm_opportunity_stage_history
            (opportunity_id, from_stage, to_stage, changed_by, changed_at)
        SELECT
            id,
            NULL,
            stage,
            COALESCE(created_by, 'Migration'),
            COALESCE(stage_entered_at, created_at)
        FROM crm_opportunities
        """
    )


def downgrade():
    op.drop_index(
        op.f("ix_crm_opportunity_stage_history_changed_at"),
        table_name="crm_opportunity_stage_history",
    )
    op.drop_index(
        op.f("ix_crm_opportunity_stage_history_to_stage"),
        table_name="crm_opportunity_stage_history",
    )
    op.drop_index(
        op.f("ix_crm_opportunity_stage_history_from_stage"),
        table_name="crm_opportunity_stage_history",
    )
    op.drop_index(
        op.f("ix_crm_opportunity_stage_history_opportunity_id"),
        table_name="crm_opportunity_stage_history",
    )
    op.drop_index(
        op.f("ix_crm_opportunity_stage_history_id"),
        table_name="crm_opportunity_stage_history",
    )
    op.drop_table("crm_opportunity_stage_history")

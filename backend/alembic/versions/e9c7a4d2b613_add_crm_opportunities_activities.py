"""Add CRM opportunities and activities

Revision ID: e9c7a4d2b613
Revises: d7c4a9e2f615
Create Date: 2026-07-24 20:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e9c7a4d2b613"
down_revision: Union[str, Sequence[str], None] = "d7c4a9e2f615"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crm_opportunities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("site_address_id", sa.Integer(), nullable=True),
        sa.Column("owner_user_id", sa.Integer(), nullable=True),
        sa.Column("sale_order_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("origin", sa.String(), nullable=True),
        sa.Column("need_type", sa.String(), server_default="autre", nullable=False),
        sa.Column("stage", sa.String(), server_default="nouveau", nullable=False),
        sa.Column("estimated_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("probability", sa.Integer(), server_default="10", nullable=False),
        sa.Column("next_milestone", sa.String(), nullable=True),
        sa.Column("next_milestone_at", sa.DateTime(), nullable=True),
        sa.Column("expected_close_date", sa.DateTime(), nullable=True),
        sa.Column("loss_reason", sa.Text(), nullable=True),
        sa.Column("won_at", sa.DateTime(), nullable=True),
        sa.Column("lost_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "probability >= 0 AND probability <= 100",
            name="ck_crm_opportunities_probability",
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["clients.id"],
            name="fk_crm_opportunities_client_id_clients",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name="fk_crm_opportunities_owner_user_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["sale_order_id"],
            ["sale_orders.id"],
            name="fk_crm_opportunities_sale_order_id_sale_orders",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["site_address_id"],
            ["client_site_addresses.id"],
            name="fk_crm_opportunities_site_address_id_client_sites",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference", name="uq_crm_opportunities_reference"),
    )
    for index_name, columns, unique in (
        ("ix_crm_opportunities_id", ["id"], False),
        ("ix_crm_opportunities_reference", ["reference"], True),
        ("ix_crm_opportunities_client_id", ["client_id"], False),
        ("ix_crm_opportunities_site_address_id", ["site_address_id"], False),
        ("ix_crm_opportunities_owner_user_id", ["owner_user_id"], False),
        ("ix_crm_opportunities_sale_order_id", ["sale_order_id"], False),
        ("ix_crm_opportunities_origin", ["origin"], False),
        ("ix_crm_opportunities_need_type", ["need_type"], False),
        ("ix_crm_opportunities_stage", ["stage"], False),
        ("ix_crm_opportunities_next_milestone_at", ["next_milestone_at"], False),
    ):
        op.create_index(index_name, "crm_opportunities", columns, unique=unique)

    op.create_table(
        "crm_activities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=True),
        sa.Column("activity_type", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(), server_default="a_faire", nullable=False),
        sa.Column("author", sa.String(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["clients.id"],
            name="fk_crm_activities_client_id_clients",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["crm_opportunities.id"],
            name="fk_crm_activities_opportunity_id_opportunities",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for index_name, columns in (
        ("ix_crm_activities_id", ["id"]),
        ("ix_crm_activities_client_id", ["client_id"]),
        ("ix_crm_activities_opportunity_id", ["opportunity_id"]),
        ("ix_crm_activities_activity_type", ["activity_type"]),
        ("ix_crm_activities_due_at", ["due_at"]),
        ("ix_crm_activities_status", ["status"]),
    ):
        op.create_index(index_name, "crm_activities", columns, unique=False)

    with op.batch_alter_table("measure_missions") as batch_op:
        batch_op.add_column(sa.Column("opportunity_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_measure_missions_opportunity_id_crm_opportunities",
            "crm_opportunities",
            ["opportunity_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_measure_missions_opportunity_id",
            ["opportunity_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("measure_missions") as batch_op:
        batch_op.drop_index("ix_measure_missions_opportunity_id")
        batch_op.drop_constraint(
            "fk_measure_missions_opportunity_id_crm_opportunities",
            type_="foreignkey",
        )
        batch_op.drop_column("opportunity_id")

    for index_name in (
        "ix_crm_activities_status",
        "ix_crm_activities_due_at",
        "ix_crm_activities_activity_type",
        "ix_crm_activities_opportunity_id",
        "ix_crm_activities_client_id",
        "ix_crm_activities_id",
    ):
        op.drop_index(index_name, table_name="crm_activities")
    op.drop_table("crm_activities")

    for index_name in (
        "ix_crm_opportunities_next_milestone_at",
        "ix_crm_opportunities_stage",
        "ix_crm_opportunities_need_type",
        "ix_crm_opportunities_origin",
        "ix_crm_opportunities_sale_order_id",
        "ix_crm_opportunities_owner_user_id",
        "ix_crm_opportunities_site_address_id",
        "ix_crm_opportunities_client_id",
        "ix_crm_opportunities_reference",
        "ix_crm_opportunities_id",
    ):
        op.drop_index(index_name, table_name="crm_opportunities")
    op.drop_table("crm_opportunities")

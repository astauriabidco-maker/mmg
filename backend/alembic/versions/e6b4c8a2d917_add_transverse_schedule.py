"""add transverse schedule

Revision ID: e6b4c8a2d917
Revises: d5a9c2e7f341
Create Date: 2026-07-25 18:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "e6b4c8a2d917"
down_revision = "d5a9c2e7f341"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("planning") as batch_op:
        batch_op.add_column(sa.Column("scheduled_start", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("scheduled_end", sa.DateTime(), nullable=True))
        batch_op.create_index(
            "ix_planning_scheduled_start",
            ["scheduled_start"],
            unique=False,
        )

    with op.batch_alter_table("crm_activities") as batch_op:
        batch_op.add_column(sa.Column("assigned_user_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            "ix_crm_activities_assigned_user_id",
            ["assigned_user_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_crm_activities_assigned_user",
            "users",
            ["assigned_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "calendar_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(), server_default="TASK", nullable=False),
        sa.Column("status", sa.String(), server_default="TODO", nullable=False),
        sa.Column("priority", sa.String(), server_default="NORMAL", nullable=False),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=True),
        sa.Column("assigned_user_id", sa.Integer(), nullable=True),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("opportunity_id", sa.Integer(), nullable=True),
        sa.Column("sale_order_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assigned_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["crm_opportunities.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["sale_order_id"],
            ["sale_orders.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_calendar_tasks_id", ["id"]),
        ("ix_calendar_tasks_category", ["category"]),
        ("ix_calendar_tasks_status", ["status"]),
        ("ix_calendar_tasks_priority", ["priority"]),
        ("ix_calendar_tasks_start_at", ["start_at"]),
        ("ix_calendar_tasks_assigned_user_id", ["assigned_user_id"]),
        ("ix_calendar_tasks_client_id", ["client_id"]),
        ("ix_calendar_tasks_opportunity_id", ["opportunity_id"]),
        ("ix_calendar_tasks_sale_order_id", ["sale_order_id"]),
    ):
        op.create_index(name, "calendar_tasks", columns, unique=False)


def downgrade():
    for name in (
        "ix_calendar_tasks_sale_order_id",
        "ix_calendar_tasks_opportunity_id",
        "ix_calendar_tasks_client_id",
        "ix_calendar_tasks_assigned_user_id",
        "ix_calendar_tasks_start_at",
        "ix_calendar_tasks_priority",
        "ix_calendar_tasks_status",
        "ix_calendar_tasks_category",
        "ix_calendar_tasks_id",
    ):
        op.drop_index(name, table_name="calendar_tasks")
    op.drop_table("calendar_tasks")

    with op.batch_alter_table("crm_activities") as batch_op:
        batch_op.drop_constraint(
            "fk_crm_activities_assigned_user",
            type_="foreignkey",
        )
        batch_op.drop_index("ix_crm_activities_assigned_user_id")
        batch_op.drop_column("assigned_user_id")

    with op.batch_alter_table("planning") as batch_op:
        batch_op.drop_index("ix_planning_scheduled_start")
        batch_op.drop_column("scheduled_end")
        batch_op.drop_column("scheduled_start")

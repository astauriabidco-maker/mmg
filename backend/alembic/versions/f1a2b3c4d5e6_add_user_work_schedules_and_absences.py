"""add user work schedules and absences

Revision ID: f1a2b3c4d5e6
Revises: e6b4c8a2d917
Create Date: 2026-07-25 19:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "f1a2b3c4d5e6"
down_revision = "e6b4c8a2d917"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "weekly_hours",
                sa.Float(),
                nullable=False,
                server_default="35",
            )
        )
        batch_op.add_column(sa.Column("work_schedule", sa.JSON(), nullable=True))

    op.create_table(
        "user_absences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=False),
        sa.Column(
            "absence_type",
            sa.String(),
            nullable=False,
            server_default="LEAVE",
        ),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="APPROVED",
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_absences_id",
        "user_absences",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_user_absences_user_id",
        "user_absences",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_absences_start_at",
        "user_absences",
        ["start_at"],
        unique=False,
    )
    op.create_index(
        "ix_user_absences_end_at",
        "user_absences",
        ["end_at"],
        unique=False,
    )


def downgrade():
    for name in (
        "ix_user_absences_end_at",
        "ix_user_absences_start_at",
        "ix_user_absences_user_id",
        "ix_user_absences_id",
    ):
        op.drop_index(name, table_name="user_absences")
    op.drop_table("user_absences")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("work_schedule")
        batch_op.drop_column("weekly_hours")

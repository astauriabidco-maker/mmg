"""add industrial planning foundation

Revision ID: f9c8b7a6d5e4
Revises: f1a2b3c4d5e6
Create Date: 2026-07-25 21:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime


revision = "f9c8b7a6d5e4"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def _create_indexes(table_name, definitions):
    for name, columns, unique in definitions:
        op.create_index(name, table_name, columns, unique=unique)


def upgrade():
    with op.batch_alter_table("user_absences") as batch_op:
        batch_op.add_column(
            sa.Column(
                "requested_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )
        batch_op.add_column(
            sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("review_note", sa.Text(), nullable=True))
        batch_op.alter_column(
            "status",
            existing_type=sa.String(),
            existing_nullable=False,
            server_default="PENDING",
        )
        batch_op.create_foreign_key(
            "fk_user_absences_reviewed_by_user",
            "users",
            ["reviewed_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_user_absences_status",
            ["status"],
            unique=False,
        )
        batch_op.create_index(
            "ix_user_absences_reviewed_by_user_id",
            ["reviewed_by_user_id"],
            unique=False,
        )

    with op.batch_alter_table("calendar_tasks") as batch_op:
        batch_op.add_column(sa.Column("location_label", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("location_address", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("latitude", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("longitude", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("workload_minutes", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "required_headcount",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        for column_name in (
            "travel_minutes_before",
            "travel_minutes_after",
            "buffer_minutes_before",
            "buffer_minutes_after",
        ):
            batch_op.add_column(
                sa.Column(
                    column_name,
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                )
            )

    op.create_table(
        "planning_skills",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "category",
            sa.String(),
            nullable=False,
            server_default="TRADE",
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "requires_expiry",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_planning_skills_code"),
    )
    _create_indexes(
        "planning_skills",
        (
            ("ix_planning_skills_id", ["id"], False),
            ("ix_planning_skills_code", ["code"], True),
            ("ix_planning_skills_category", ["category"], False),
            ("ix_planning_skills_is_active", ["is_active"], False),
        ),
    )

    skill_table = sa.table(
        "planning_skills",
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("category", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("requires_expiry", sa.Boolean()),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
    )
    op.bulk_insert(
        skill_table,
        [
            {
                "code": "METREUR",
                "name": "Métreur",
                "category": "TRADE",
                "description": "Prise de cotes et relevé chantier.",
                "requires_expiry": False,
                "is_active": True,
                "created_at": datetime.utcnow(),
            },
            {
                "code": "POSEUR",
                "name": "Poseur",
                "category": "TRADE",
                "description": "Installation et pose sur chantier.",
                "requires_expiry": False,
                "is_active": True,
                "created_at": datetime.utcnow(),
            },
            {
                "code": "DEBIT_PVC",
                "name": "Débit PVC",
                "category": "WORKSHOP",
                "description": "Débit et préparation des profils PVC.",
                "requires_expiry": False,
                "is_active": True,
                "created_at": datetime.utcnow(),
            },
            {
                "code": "DEBIT_ALU",
                "name": "Débit ALU",
                "category": "WORKSHOP",
                "description": "Débit et préparation des profils aluminium.",
                "requires_expiry": False,
                "is_active": True,
                "created_at": datetime.utcnow(),
            },
            {
                "code": "PERMIS",
                "name": "Permis de conduire",
                "category": "LICENSE",
                "description": "Permis requis pour la ressource véhicule affectée.",
                "requires_expiry": True,
                "is_active": True,
                "created_at": datetime.utcnow(),
            },
            {
                "code": "HABILITATION",
                "name": "Habilitation",
                "category": "CERTIFICATION",
                "description": "Habilitation métier ou sécurité contrôlée.",
                "requires_expiry": True,
                "is_active": True,
                "created_at": datetime.utcnow(),
            },
        ],
    )

    op.create_table(
        "user_planning_skills",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "is_certified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("certificate_reference", sa.String(), nullable=True),
        sa.Column("acquired_at", sa.DateTime(), nullable=True),
        sa.Column("valid_until", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["skill_id"], ["planning_skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "skill_id",
            name="uq_user_planning_skills_user_skill",
        ),
    )
    _create_indexes(
        "user_planning_skills",
        (
            ("ix_user_planning_skills_user_id", ["user_id"], False),
            ("ix_user_planning_skills_skill_id", ["skill_id"], False),
            ("ix_user_planning_skills_valid_until", ["valid_until"], False),
        ),
    )

    op.create_table(
        "planning_resources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("resource_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="ACTIVE"),
        sa.Column("station_id", sa.Integer(), nullable=True),
        sa.Column("capacity", sa.Float(), nullable=False, server_default="1"),
        sa.Column(
            "timezone",
            sa.String(),
            nullable=False,
            server_default="Europe/Paris",
        ),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_planning_resources_code"),
    )
    _create_indexes(
        "planning_resources",
        (
            ("ix_planning_resources_id", ["id"], False),
            ("ix_planning_resources_code", ["code"], True),
            ("ix_planning_resources_name", ["name"], False),
            ("ix_planning_resources_resource_type", ["resource_type"], False),
            ("ix_planning_resources_status", ["status"], False),
            ("ix_planning_resources_station_id", ["station_id"], False),
            ("ix_planning_resources_is_active", ["is_active"], False),
        ),
    )

    op.create_table(
        "planning_resource_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("member_role", sa.String(), nullable=True),
        sa.Column(
            "is_lead",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["planning_resources.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "resource_id",
            "user_id",
            name="uq_planning_resource_members_resource_user",
        ),
    )
    _create_indexes(
        "planning_resource_members",
        (
            ("ix_planning_resource_members_resource_id", ["resource_id"], False),
            ("ix_planning_resource_members_user_id", ["user_id"], False),
        ),
    )

    op.create_table(
        "planning_resource_unavailabilities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "unavailability_type",
            sa.String(),
            nullable=False,
            server_default="UNAVAILABLE",
        ),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["planning_resources.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_indexes(
        "planning_resource_unavailabilities",
        (
            (
                "ix_planning_resource_unavailability_window",
                ["resource_id", "start_at", "end_at"],
                False,
            ),
            (
                "ix_planning_resource_unavailabilities_resource_id",
                ["resource_id"],
                False,
            ),
            (
                "ix_planning_resource_unavailabilities_start_at",
                ["start_at"],
                False,
            ),
            (
                "ix_planning_resource_unavailabilities_end_at",
                ["end_at"],
                False,
            ),
            (
                "ix_planning_resource_unavailabilities_unavailability_type",
                ["unavailability_type"],
                False,
            ),
        ),
    )

    op.create_table(
        "planning_closures",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "closure_type",
            sa.String(),
            nullable=False,
            server_default="PUBLIC_HOLIDAY",
        ),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=False),
        sa.Column(
            "all_day",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("country_code", sa.String(length=2), nullable=False, server_default="FR"),
        sa.Column("scope_type", sa.String(), nullable=False, server_default="GLOBAL"),
        sa.Column("team", sa.String(), nullable=True),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column(
            "affects_capacity",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["planning_resources.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_indexes(
        "planning_closures",
        (
            ("ix_planning_closures_id", ["id"], False),
            ("ix_planning_closures_window", ["start_at", "end_at"], False),
            ("ix_planning_closures_closure_type", ["closure_type"], False),
            ("ix_planning_closures_start_at", ["start_at"], False),
            ("ix_planning_closures_end_at", ["end_at"], False),
            ("ix_planning_closures_scope_type", ["scope_type"], False),
            ("ix_planning_closures_team", ["team"], False),
            ("ix_planning_closures_resource_id", ["resource_id"], False),
        ),
    )

    op.create_table(
        "calendar_task_skill_requirements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("minimum_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "is_mandatory",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["planning_skills.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["calendar_tasks.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id",
            "skill_id",
            name="uq_calendar_task_skill_requirements_task_skill",
        ),
    )
    _create_indexes(
        "calendar_task_skill_requirements",
        (
            (
                "ix_calendar_task_skill_requirements_task_id",
                ["task_id"],
                False,
            ),
            (
                "ix_calendar_task_skill_requirements_skill_id",
                ["skill_id"],
                False,
            ),
        ),
    )

    op.create_table(
        "calendar_task_resource_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(), nullable=False, server_default="REQUIRED"),
        sa.Column("assigned_by_user_id", sa.Integer(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(), nullable=False),
        sa.Column("released_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["assigned_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["planning_resources.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["calendar_tasks.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id",
            "resource_id",
            name="uq_calendar_task_resource_assignments_task_resource",
        ),
    )
    _create_indexes(
        "calendar_task_resource_assignments",
        (
            (
                "ix_calendar_task_resource_assignments_task_id",
                ["task_id"],
                False,
            ),
            (
                "ix_calendar_task_resource_assignments_resource_id",
                ["resource_id"],
                False,
            ),
            (
                "ix_calendar_task_resource_assignments_assigned_by_user_id",
                ["assigned_by_user_id"],
                False,
            ),
            (
                "ix_calendar_task_resource_assignments_status",
                ["status"],
                False,
            ),
            (
                "ix_calendar_task_resource_assignments_resource_status",
                ["resource_id", "status"],
                False,
            ),
        ),
    )

    op.create_table(
        "planning_change_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("source_screen", sa.String(), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["calendar_tasks.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_indexes(
        "planning_change_logs",
        (
            ("ix_planning_change_logs_id", ["id"], False),
            ("ix_planning_change_logs_task_id", ["task_id"], False),
            ("ix_planning_change_logs_action", ["action"], False),
            ("ix_planning_change_logs_actor_user_id", ["actor_user_id"], False),
            ("ix_planning_change_logs_created_at", ["created_at"], False),
            (
                "ix_planning_change_logs_task_created",
                ["task_id", "created_at"],
                False,
            ),
        ),
    )

    op.create_table(
        "planning_notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column(
            "notification_type",
            sa.String(),
            nullable=False,
            server_default="ASSIGNMENT",
        ),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="UNREAD"),
        sa.Column("deduplication_key", sa.String(), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["calendar_tasks.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "deduplication_key",
            name="uq_planning_notifications_deduplication_key",
        ),
    )
    _create_indexes(
        "planning_notifications",
        (
            ("ix_planning_notifications_id", ["id"], False),
            ("ix_planning_notifications_user_id", ["user_id"], False),
            ("ix_planning_notifications_task_id", ["task_id"], False),
            (
                "ix_planning_notifications_notification_type",
                ["notification_type"],
                False,
            ),
            ("ix_planning_notifications_status", ["status"], False),
            (
                "ix_planning_notifications_deduplication_key",
                ["deduplication_key"],
                True,
            ),
            ("ix_planning_notifications_created_at", ["created_at"], False),
            (
                "ix_planning_notifications_inbox",
                ["user_id", "status", "created_at"],
                False,
            ),
        ),
    )


def downgrade():
    for table_name in (
        "planning_notifications",
        "planning_change_logs",
        "calendar_task_resource_assignments",
        "calendar_task_skill_requirements",
        "planning_closures",
        "planning_resource_unavailabilities",
        "planning_resource_members",
        "user_planning_skills",
        "planning_resources",
        "planning_skills",
    ):
        op.drop_table(table_name)

    with op.batch_alter_table("calendar_tasks") as batch_op:
        for column_name in (
            "buffer_minutes_after",
            "buffer_minutes_before",
            "travel_minutes_after",
            "travel_minutes_before",
            "required_headcount",
            "workload_minutes",
            "longitude",
            "latitude",
            "location_address",
            "location_label",
        ):
            batch_op.drop_column(column_name)

    with op.batch_alter_table("user_absences") as batch_op:
        batch_op.drop_index("ix_user_absences_reviewed_by_user_id")
        batch_op.drop_index("ix_user_absences_status")
        batch_op.drop_constraint(
            "fk_user_absences_reviewed_by_user",
            type_="foreignkey",
        )
        batch_op.alter_column(
            "status",
            existing_type=sa.String(),
            existing_nullable=False,
            server_default="APPROVED",
        )
        batch_op.drop_column("review_note")
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("reviewed_by_user_id")
        batch_op.drop_column("requested_at")

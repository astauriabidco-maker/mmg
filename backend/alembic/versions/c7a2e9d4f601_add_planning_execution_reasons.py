"""add planning execution reasons

Revision ID: c7a2e9d4f601
Revises: b4e7c1a9d203
Create Date: 2026-07-26 21:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "c7a2e9d4f601"
down_revision = "b4e7c1a9d203"
branch_labels = None
depends_on = None


DEFAULT_REASONS = (
    ("PAUSE", "REGULATORY_BREAK", "Pause réglementaire", 10, False),
    ("PAUSE", "END_OF_SHIFT", "Fin de poste", 20, False),
    ("PAUSE", "WAITING_VALIDATION", "Attente de validation", 30, False),
    ("PAUSE", "WAITING_CLIENT", "Attente client", 40, False),
    ("PAUSE", "WAITING_MATERIAL", "Attente matière", 50, False),
    ("PAUSE", "PRIORITY_CHANGE", "Changement de priorité", 60, False),
    ("PAUSE", "TRAVEL", "Déplacement", 70, False),
    ("PAUSE", "OTHER", "Autre motif", 999, True),
    ("BLOCK", "MISSING_STOCK", "Pièce ou stock manquant", 10, False),
    ("BLOCK", "MACHINE_UNAVAILABLE", "Machine indisponible", 20, False),
    ("BLOCK", "QUALITY_NONCONFORMITY", "Non-conformité qualité", 30, False),
    ("BLOCK", "MISSING_TECH_DOC", "Document technique manquant", 40, False),
    ("BLOCK", "RESOURCE_UNAVAILABLE", "Ressource indisponible", 50, False),
    ("BLOCK", "SITE_ACCESS", "Accès chantier impossible", 60, False),
    ("BLOCK", "SAFETY", "Problème de sécurité", 70, False),
    ("BLOCK", "CLIENT_ABSENT", "Client absent", 80, False),
    ("BLOCK", "OTHER", "Autre blocage", 999, True),
)


def upgrade():
    op.create_table(
        "planning_execution_reasons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "requires_comment",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default="100",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("created_by", sa.String(), nullable=False),
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
        sa.UniqueConstraint(
            "action",
            "code",
            name="uq_planning_execution_reasons_action_code",
        ),
    )
    for name, columns in (
        ("ix_planning_execution_reasons_id", ["id"]),
        ("ix_planning_execution_reasons_action", ["action"]),
        ("ix_planning_execution_reasons_code", ["code"]),
        ("ix_planning_execution_reasons_is_active", ["is_active"]),
        (
            "ix_planning_execution_reasons_action_active_order",
            ["action", "is_active", "sort_order"],
        ),
    ):
        op.create_index(
            name,
            "planning_execution_reasons",
            columns,
            unique=False,
        )

    reason_table = sa.table(
        "planning_execution_reasons",
        sa.column("action", sa.String()),
        sa.column("code", sa.String()),
        sa.column("label", sa.String()),
        sa.column("requires_comment", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_by", sa.String()),
    )
    op.bulk_insert(
        reason_table,
        [
            {
                "action": action,
                "code": code,
                "label": label,
                "sort_order": sort_order,
                "requires_comment": requires_comment,
                "is_active": True,
                "created_by": "Migration initiale",
            }
            for action, code, label, sort_order, requires_comment in DEFAULT_REASONS
        ],
    )

    with op.batch_alter_table("schedule_execution_states") as batch_op:
        batch_op.add_column(sa.Column("last_reason_code", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("last_reason_label", sa.String(), nullable=True))

    with op.batch_alter_table("schedule_execution_logs") as batch_op:
        batch_op.add_column(sa.Column("reason_code", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("reason_label", sa.String(), nullable=True))


def downgrade():
    with op.batch_alter_table("schedule_execution_logs") as batch_op:
        batch_op.drop_column("reason_label")
        batch_op.drop_column("reason_code")

    with op.batch_alter_table("schedule_execution_states") as batch_op:
        batch_op.drop_column("last_reason_label")
        batch_op.drop_column("last_reason_code")

    op.drop_table("planning_execution_reasons")

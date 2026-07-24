"""Add versioned technical dossiers between measure missions and quoting.

Revision ID: a6c9d3e7f214
Revises: f4d8b2a7c901
"""

from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = "a6c9d3e7f214"
down_revision: Union[str, None] = "f4d8b2a7c901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "measure_missions" not in tables:
        return
    if "technical_dossiers" not in tables:
        op.create_table(
            "technical_dossiers",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("reference", sa.String(), nullable=False),
            sa.Column("mission_id", sa.Integer(), nullable=False),
            sa.Column("quoting_status", sa.String(), nullable=False, server_default="DRAFT"),
            sa.Column("production_status", sa.String(), nullable=False, server_default="LOCKED"),
            sa.Column("quoting_review_note", sa.Text(), nullable=True),
            sa.Column("production_review_note", sa.Text(), nullable=True),
            sa.Column("quoting_submitted_at", sa.DateTime(), nullable=True),
            sa.Column("quoting_submitted_by", sa.String(), nullable=True),
            sa.Column("quoting_validated_at", sa.DateTime(), nullable=True),
            sa.Column("quoting_validated_by", sa.String(), nullable=True),
            sa.Column("production_submitted_at", sa.DateTime(), nullable=True),
            sa.Column("production_submitted_by", sa.String(), nullable=True),
            sa.Column("production_validated_at", sa.DateTime(), nullable=True),
            sa.Column("production_validated_by", sa.String(), nullable=True),
            sa.Column("created_by", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["mission_id"],
                ["measure_missions.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("mission_id"),
            sa.UniqueConstraint("reference"),
        )
        op.create_index("ix_technical_dossiers_id", "technical_dossiers", ["id"])
        op.create_index("ix_technical_dossiers_reference", "technical_dossiers", ["reference"])
        op.create_index("ix_technical_dossiers_mission_id", "technical_dossiers", ["mission_id"])
        op.create_index("ix_technical_dossiers_quoting_status", "technical_dossiers", ["quoting_status"])
        op.create_index("ix_technical_dossiers_production_status", "technical_dossiers", ["production_status"])

    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "technical_dossier_versions" not in tables:
        op.create_table(
            "technical_dossier_versions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("dossier_id", sa.Integer(), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("document_type", sa.String(), nullable=False, server_default="QUOTING"),
            sa.Column("source_system", sa.String(), nullable=False),
            sa.Column("source_reference", sa.String(), nullable=True),
            sa.Column("original_filename", sa.String(), nullable=False),
            sa.Column("stored_filename", sa.String(), nullable=False),
            sa.Column("content_type", sa.String(), nullable=True),
            sa.Column("file_path", sa.String(), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("checksum_sha256", sa.String(), nullable=False),
            sa.Column("opening_ids", sa.JSON(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["dossier_id"],
                ["technical_dossiers.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "dossier_id",
                "version_number",
                name="uq_technical_dossier_versions_number",
            ),
        )
        op.create_index("ix_technical_dossier_versions_id", "technical_dossier_versions", ["id"])
        op.create_index(
            "ix_technical_dossier_versions_document_type",
            "technical_dossier_versions",
            ["document_type"],
        )
        op.create_index(
            "ix_technical_dossier_versions_dossier_id",
            "technical_dossier_versions",
            ["dossier_id"],
        )
        op.create_index(
            "ix_technical_dossier_versions_source_system",
            "technical_dossier_versions",
            ["source_system"],
        )
        op.create_index(
            "ix_technical_dossier_versions_checksum_sha256",
            "technical_dossier_versions",
            ["checksum_sha256"],
        )

    bind = op.get_bind()
    existing_mission_ids = {
        row[0]
        for row in bind.execute(sa.text("SELECT mission_id FROM technical_dossiers"))
    }
    legacy_missions = bind.execute(
        sa.text(
            "SELECT id, created_by FROM measure_missions "
            "WHERE status IN ('VALIDATED', 'QUOTED')"
        )
    ).fetchall()
    now = datetime.utcnow()
    for mission_id, created_by in legacy_missions:
        if mission_id in existing_mission_ids:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO technical_dossiers "
                "(reference, mission_id, quoting_status, production_status, created_by, created_at, updated_at) "
                "VALUES (:reference, :mission_id, 'DRAFT', 'LOCKED', :created_by, :created_at, :updated_at)"
            ),
            {
                "reference": f"DT-MIG-{mission_id:05d}",
                "mission_id": mission_id,
                "created_by": created_by or "Migration",
                "created_at": now,
                "updated_at": now,
            },
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "technical_dossier_versions" in tables:
        op.drop_table("technical_dossier_versions")
    inspector = sa.inspect(op.get_bind())
    if "technical_dossiers" in set(inspector.get_table_names()):
        op.drop_table("technical_dossiers")

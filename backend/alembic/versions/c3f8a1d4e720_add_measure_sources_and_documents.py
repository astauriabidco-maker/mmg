"""Add measure sources, verification and source documents

Revision ID: c3f8a1d4e720
Revises: b9e4c7a2d615
Create Date: 2026-07-24 16:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3f8a1d4e720"
down_revision: Union[str, Sequence[str], None] = "b9e4c7a2d615"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _columns(table_name: str) -> set[str]:
    if not _inspector().has_table(table_name):
        return set()
    return {column["name"] for column in _inspector().get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    if not _inspector().has_table(table_name):
        return set()
    return {index["name"] for index in _inspector().get_indexes(table_name)}


def upgrade() -> None:
    mission_columns = _columns("measure_missions")
    additions = (
        ("source_type", sa.Column("source_type", sa.String(), server_default="SITE_VISIT", nullable=False)),
        ("project_scope", sa.Column("project_scope", sa.String(), server_default="SUPPLY_AND_INSTALL", nullable=False)),
        ("verification_status", sa.Column("verification_status", sa.String(), server_default="UNVERIFIED", nullable=False)),
        ("client_approved_at", sa.Column("client_approved_at", sa.DateTime(), nullable=True)),
        ("client_approved_by", sa.Column("client_approved_by", sa.String(), nullable=True)),
        ("site_verified_at", sa.Column("site_verified_at", sa.DateTime(), nullable=True)),
        ("site_verified_by", sa.Column("site_verified_by", sa.String(), nullable=True)),
    )
    with op.batch_alter_table("measure_missions") as batch_op:
        for name, column in additions:
            if name not in mission_columns:
                batch_op.add_column(column)

    for index_name, column in (
        ("ix_measure_missions_source_type", "source_type"),
        ("ix_measure_missions_verification_status", "verification_status"),
    ):
        if index_name not in _indexes("measure_missions"):
            op.create_index(index_name, "measure_missions", [column], unique=False)

    if not _inspector().has_table("measure_mission_documents"):
        op.create_table(
            "measure_mission_documents",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("mission_id", sa.Integer(), nullable=False),
            sa.Column("original_filename", sa.String(), nullable=False),
            sa.Column("stored_filename", sa.String(), nullable=False),
            sa.Column("content_type", sa.String(), nullable=True),
            sa.Column("file_path", sa.String(), nullable=False),
            sa.Column("file_size", sa.Integer(), server_default="0", nullable=True),
            sa.Column("document_type", sa.String(), server_default="SOURCE_MEASURE", nullable=True),
            sa.Column("uploaded_by", sa.String(), nullable=True),
            sa.Column("uploaded_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(
                ["mission_id"],
                ["measure_missions.id"],
                name="fk_measure_mission_documents_mission_id",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_measure_mission_documents_id",
            "measure_mission_documents",
            ["id"],
            unique=False,
        )
        op.create_index(
            "ix_measure_mission_documents_mission_id",
            "measure_mission_documents",
            ["mission_id"],
            unique=False,
        )


def downgrade() -> None:
    if _inspector().has_table("measure_mission_documents"):
        op.drop_table("measure_mission_documents")
    for index_name in (
        "ix_measure_missions_verification_status",
        "ix_measure_missions_source_type",
    ):
        if index_name in _indexes("measure_missions"):
            op.drop_index(index_name, table_name="measure_missions")
    mission_columns = _columns("measure_missions")
    with op.batch_alter_table("measure_missions") as batch_op:
        for name in (
            "site_verified_by",
            "site_verified_at",
            "client_approved_by",
            "client_approved_at",
            "verification_status",
            "project_scope",
            "source_type",
        ):
            if name in mission_columns:
                batch_op.drop_column(name)

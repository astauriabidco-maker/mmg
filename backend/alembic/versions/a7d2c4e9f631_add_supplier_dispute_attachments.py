"""Add supplier dispute attachments

Revision ID: a7d2c4e9f631
Revises: f0d7c2a9e514
Create Date: 2026-07-24 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7d2c4e9f631"
down_revision: Union[str, Sequence[str], None] = "f0d7c2a9e514"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str], unique: bool = False) -> None:
    if _has_table(table_name) and not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    if not _has_table("supplier_dispute_attachments"):
        op.create_table(
            "supplier_dispute_attachments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("dispute_id", sa.Integer(), nullable=False),
            sa.Column("original_filename", sa.String(), nullable=False),
            sa.Column("stored_filename", sa.String(), nullable=False),
            sa.Column("content_type", sa.String(), nullable=True),
            sa.Column("file_path", sa.String(), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=True),
            sa.Column("uploaded_by", sa.String(), nullable=True),
            sa.Column("uploaded_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["dispute_id"], ["supplier_disputes.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_supplier_dispute_attachments_id", "supplier_dispute_attachments", ["id"])
    _create_index_if_missing("ix_supplier_dispute_attachments_dispute_id", "supplier_dispute_attachments", ["dispute_id"])

    if not _has_table("supplier_dispute_events"):
        op.create_table(
            "supplier_dispute_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("dispute_id", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(), nullable=False),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("actor", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["dispute_id"], ["supplier_disputes.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_supplier_dispute_events_id", "supplier_dispute_events", ["id"])
    _create_index_if_missing("ix_supplier_dispute_events_dispute_id", "supplier_dispute_events", ["dispute_id"])
    _create_index_if_missing("ix_supplier_dispute_events_event_type", "supplier_dispute_events", ["event_type"])


def downgrade() -> None:
    if _has_table("supplier_dispute_events"):
        for index_name in [
            "ix_supplier_dispute_events_event_type",
            "ix_supplier_dispute_events_dispute_id",
            "ix_supplier_dispute_events_id",
        ]:
            if _has_index("supplier_dispute_events", index_name):
                op.drop_index(index_name, table_name="supplier_dispute_events")
        op.drop_table("supplier_dispute_events")

    if _has_table("supplier_dispute_attachments"):
        for index_name in [
            "ix_supplier_dispute_attachments_dispute_id",
            "ix_supplier_dispute_attachments_id",
        ]:
            if _has_index("supplier_dispute_attachments", index_name):
                op.drop_index(index_name, table_name="supplier_dispute_attachments")
        op.drop_table("supplier_dispute_attachments")

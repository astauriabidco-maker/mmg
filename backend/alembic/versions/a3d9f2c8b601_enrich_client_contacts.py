"""Enrich CRM client contacts.

Revision ID: a3d9f2c8b601
Revises: a2c4e6f8b103
Create Date: 2026-09-02 19:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3d9f2c8b601"
down_revision: Union[str, Sequence[str], None] = "a2c4e6f8b103"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("client_contacts"):
        return
    columns = {column["name"] for column in inspector.get_columns("client_contacts")}
    with op.batch_alter_table("client_contacts") as batch_op:
        if "priority" not in columns:
            batch_op.add_column(
                sa.Column(
                    "priority",
                    sa.Integer(),
                    nullable=False,
                    server_default="3",
                )
            )
        if "influence_role" not in columns:
            batch_op.add_column(sa.Column("influence_role", sa.String(), nullable=True))
        if "preferred_channel" not in columns:
            batch_op.add_column(sa.Column("preferred_channel", sa.String(), nullable=True))
        if "email_consent" not in columns:
            batch_op.add_column(
                sa.Column(
                    "email_consent",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )
        if "email_consent_at" not in columns:
            batch_op.add_column(sa.Column("email_consent_at", sa.DateTime(), nullable=True))

    indexes = {index["name"] for index in inspector.get_indexes("client_contacts")}
    if "ix_client_contacts_priority" not in indexes:
        op.create_index("ix_client_contacts_priority", "client_contacts", ["priority"], unique=False)
    if "ix_client_contacts_influence_role" not in indexes:
        op.create_index(
            "ix_client_contacts_influence_role",
            "client_contacts",
            ["influence_role"],
            unique=False,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("client_contacts"):
        return
    indexes = {index["name"] for index in inspector.get_indexes("client_contacts")}
    if "ix_client_contacts_influence_role" in indexes:
        op.drop_index("ix_client_contacts_influence_role", table_name="client_contacts")
    if "ix_client_contacts_priority" in indexes:
        op.drop_index("ix_client_contacts_priority", table_name="client_contacts")
    columns = {column["name"] for column in inspector.get_columns("client_contacts")}
    with op.batch_alter_table("client_contacts") as batch_op:
        for name in (
            "email_consent_at",
            "email_consent",
            "preferred_channel",
            "influence_role",
            "priority",
        ):
            if name in columns:
                batch_op.drop_column(name)

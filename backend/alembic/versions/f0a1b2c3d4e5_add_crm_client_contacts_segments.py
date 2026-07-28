"""Add CRM client contacts, segmentation and tags.

Revision ID: f0a1b2c3d4e5
Revises: e9c5a2d7f104
Create Date: 2026-07-28 10:00:00.000000
"""

from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "e9c5a2d7f104"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("segment", sa.String(), nullable=True))
    op.add_column(
        "clients",
        sa.Column(
            "tags",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.create_index("ix_clients_segment", "clients", ["segment"], unique=False)

    op.create_table(
        "client_contacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "client_id",
            sa.Integer(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_client_contacts_client_id",
        "client_contacts",
        ["client_id"],
        unique=False,
    )
    op.create_index(
        "ix_client_contacts_email",
        "client_contacts",
        ["email"],
        unique=False,
    )
    op.create_index(
        "ix_client_contacts_phone",
        "client_contacts",
        ["phone"],
        unique=False,
    )
    op.create_index(
        "ix_client_contacts_is_primary",
        "client_contacts",
        ["is_primary"],
        unique=False,
    )

    bind = op.get_bind()
    clients = sa.table(
        "clients",
        sa.column("id", sa.Integer()),
        sa.column("contact_name", sa.String()),
        sa.column("email", sa.String()),
        sa.column("phone", sa.String()),
        sa.column("created_at", sa.DateTime()),
    )
    contacts = sa.table(
        "client_contacts",
        sa.column("client_id", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("role", sa.String()),
        sa.column("email", sa.String()),
        sa.column("phone", sa.String()),
        sa.column("is_primary", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    for row in bind.execute(
        sa.select(
            clients.c.id,
            clients.c.contact_name,
            clients.c.email,
            clients.c.phone,
            clients.c.created_at,
        )
    ).mappings():
        if not any((row["contact_name"], row["email"], row["phone"])):
            continue
        timestamp = row["created_at"] or datetime.utcnow()
        bind.execute(
            contacts.insert().values(
                client_id=row["id"],
                name=row["contact_name"] or row["email"] or row["phone"],
                role="Contact principal",
                email=row["email"],
                phone=row["phone"],
                is_primary=True,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )


def downgrade() -> None:
    op.drop_index("ix_client_contacts_is_primary", table_name="client_contacts")
    op.drop_index("ix_client_contacts_phone", table_name="client_contacts")
    op.drop_index("ix_client_contacts_email", table_name="client_contacts")
    op.drop_index("ix_client_contacts_client_id", table_name="client_contacts")
    op.drop_table("client_contacts")
    op.drop_index("ix_clients_segment", table_name="clients")
    op.drop_column("clients", "tags")
    op.drop_column("clients", "segment")

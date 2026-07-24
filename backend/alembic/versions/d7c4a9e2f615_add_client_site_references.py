"""Add generated references to client sites

Revision ID: d7c4a9e2f615
Revises: b2e6f8a1c407
Create Date: 2026-07-24 18:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7c4a9e2f615"
down_revision: Union[str, Sequence[str], None] = "b2e6f8a1c407"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("client_site_addresses")}
    if "reference" not in columns:
        op.add_column("client_site_addresses", sa.Column("reference", sa.String(), nullable=True))
        sites = sa.table(
            "client_site_addresses",
            sa.column("id", sa.Integer()),
            sa.column("reference", sa.String()),
        )
        rows = op.get_bind().execute(sa.select(sites.c.id).order_by(sites.c.id)).all()
        for site_id, in rows:
            op.get_bind().execute(
                sites.update()
                .where(sites.c.id == site_id)
                .values(reference=f"CH-LEGACY-{site_id:04d}")
            )
        with op.batch_alter_table("client_site_addresses") as batch_op:
            batch_op.alter_column("reference", existing_type=sa.String(), nullable=False)

    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("client_site_addresses")}
    if "ix_client_site_addresses_reference" not in indexes:
        op.create_index(
            "ix_client_site_addresses_reference",
            "client_site_addresses",
            ["reference"],
            unique=True,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    indexes = {index["name"] for index in inspector.get_indexes("client_site_addresses")}
    if "ix_client_site_addresses_reference" in indexes:
        op.drop_index("ix_client_site_addresses_reference", table_name="client_site_addresses")
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("client_site_addresses")}
    if "reference" in columns:
        op.drop_column("client_site_addresses", "reference")

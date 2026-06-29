"""Add product catalog status

Revision ID: a7c2d8e9f104
Revises: f68a21d4c9b0
Create Date: 2026-06-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7c2d8e9f104"
down_revision: Union[str, Sequence[str], None] = "f68a21d4c9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _columns("products")
    if "catalog_status" not in columns:
        op.add_column("products", sa.Column("catalog_status", sa.String(), nullable=True, server_default="ACTIVE"))
        op.create_index(op.f("ix_products_catalog_status"), "products", ["catalog_status"], unique=False)

    bind = op.get_bind()
    bind.execute(sa.text("UPDATE products SET catalog_status = 'ACTIVE' WHERE catalog_status IS NULL"))
    bind.execute(
        sa.text(
            """
            UPDATE products
            SET catalog_status = 'DRAFT'
            WHERE lower(coalesce(name, '')) LIKE '%[brouillon]%'
               OR lower(coalesce(compatible_series, '')) LIKE '%prévisualisation débit atelier%'
               OR lower(coalesce(compatible_series, '')) LIKE '%previsualisation debit atelier%'
            """
        )
    )


def downgrade() -> None:
    columns = _columns("products")
    if "catalog_status" in columns:
        op.drop_index(op.f("ix_products_catalog_status"), table_name="products")
        op.drop_column("products", "catalog_status")

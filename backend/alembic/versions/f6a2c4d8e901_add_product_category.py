"""Separate product category from material

Revision ID: f6a2c4d8e901
Revises: c3f8a1d4e720
Create Date: 2026-07-24 17:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6a2c4d8e901"
down_revision: Union[str, Sequence[str], None] = "c3f8a1d4e720"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("products"):
        return set()
    return {column["name"] for column in inspector.get_columns("products")}


def _indexes() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("products"):
        return set()
    return {index["name"] for index in inspector.get_indexes("products")}


def upgrade() -> None:
    if "category" not in _columns():
        with op.batch_alter_table("products") as batch_op:
            batch_op.add_column(sa.Column("category", sa.String(), nullable=True))

    # L'ancien champ mélangeait matière et famille. On conserve sa valeur comme
    # catégorie initiale afin de ne perdre aucun classement lors du déploiement.
    op.execute(
        """
        UPDATE products
        SET category = CASE
            WHEN product_type = 'service' THEN 'SERVICE'
            WHEN material_type IS NULL OR TRIM(material_type) = '' THEN 'AUTRE'
            ELSE material_type
        END
        WHERE category IS NULL OR TRIM(category) = ''
        """
    )

    if "ix_products_category" not in _indexes():
        op.create_index("ix_products_category", "products", ["category"], unique=False)


def downgrade() -> None:
    if "ix_products_category" in _indexes():
        op.drop_index("ix_products_category", table_name="products")
    if "category" in _columns():
        with op.batch_alter_table("products") as batch_op:
            batch_op.drop_column("category")

"""Fix stock and logistics schema drift

Revision ID: b8d3a6f4c921
Revises: 7a51ad190416
Create Date: 2026-05-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b8d3a6f4c921"
down_revision: Union[str, Sequence[str], None] = "7a51ad190416"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    """Upgrade schema."""
    product_columns = _columns("products")
    if product_columns:
        if "technical_doc_url" not in product_columns:
            op.add_column("products", sa.Column("technical_doc_url", sa.String(), nullable=True))
        if "compatible_series" not in product_columns:
            op.add_column("products", sa.Column("compatible_series", sa.String(), nullable=True))

    delivery_columns = _columns("delivery_notes")
    if delivery_columns:
        if "delivery_notes" not in delivery_columns:
            op.add_column("delivery_notes", sa.Column("delivery_notes", sa.Text(), nullable=True))
            delivery_columns.add("delivery_notes")
        if "notes" in delivery_columns:
            op.execute(
                sa.text(
                    "UPDATE delivery_notes "
                    "SET delivery_notes = notes "
                    "WHERE delivery_notes IS NULL AND notes IS NOT NULL"
                )
            )


def downgrade() -> None:
    """Downgrade schema."""
    delivery_columns = _columns("delivery_notes")
    if {"delivery_notes", "notes"}.issubset(delivery_columns):
        op.execute(
            sa.text(
                "UPDATE delivery_notes "
                "SET notes = delivery_notes "
                "WHERE notes IS NULL AND delivery_notes IS NOT NULL"
            )
        )

    product_columns = _columns("products")
    if "compatible_series" in product_columns:
        op.drop_column("products", "compatible_series")
    if "technical_doc_url" in product_columns:
        op.drop_column("products", "technical_doc_url")

    delivery_columns = _columns("delivery_notes")
    if "delivery_notes" in delivery_columns and "notes" in delivery_columns:
        op.drop_column("delivery_notes", "delivery_notes")

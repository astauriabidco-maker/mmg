"""add credit note links

Revision ID: b4d7c8f2a901
Revises: a2c9d4e5f601
Create Date: 2026-07-02 13:40:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4d7c8f2a901"
down_revision: Union[str, Sequence[str], None] = "a2c9d4e5f601"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _columns("invoices")
    if "source_invoice_id" not in columns:
        op.add_column("invoices", sa.Column("source_invoice_id", sa.Integer(), nullable=True))
    if "delivery_note_id" not in columns:
        op.add_column("invoices", sa.Column("delivery_note_id", sa.Integer(), nullable=True))
    if "return_move_id" not in columns:
        op.add_column("invoices", sa.Column("return_move_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    columns = _columns("invoices")
    if "return_move_id" in columns:
        op.drop_column("invoices", "return_move_id")
    if "delivery_note_id" in columns:
        op.drop_column("invoices", "delivery_note_id")
    if "source_invoice_id" in columns:
        op.drop_column("invoices", "source_invoice_id")

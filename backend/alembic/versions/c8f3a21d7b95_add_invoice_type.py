"""add invoice type

Revision ID: c8f3a21d7b95
Revises: b4d7c8f2a901
Create Date: 2026-07-03 13:40:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c8f3a21d7b95"
down_revision: Union[str, Sequence[str], None] = "b4d7c8f2a901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("invoices")}
    if "invoice_type" not in columns:
        op.add_column("invoices", sa.Column("invoice_type", sa.String(), nullable=True, server_default="FINAL"))
    bind.execute(sa.text("UPDATE invoices SET invoice_type = 'FINAL' WHERE invoice_type IS NULL OR invoice_type = ''"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("invoices")}
    if "invoice_type" in columns:
        op.drop_column("invoices", "invoice_type")

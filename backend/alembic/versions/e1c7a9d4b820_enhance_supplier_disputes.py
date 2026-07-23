"""Enhance supplier disputes

Revision ID: e1c7a9d4b820
Revises: d8b4f2a6c901
Create Date: 2026-07-23 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1c7a9d4b820"
down_revision: Union[str, Sequence[str], None] = "d8b4f2a6c901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if _has_table(table_name) and not _has_column(table_name, column.name):
        op.add_column(table_name, column)


def _drop_column_if_present(table_name: str, column_name: str) -> None:
    if _has_table(table_name) and _has_column(table_name, column_name):
        op.drop_column(table_name, column_name)


def upgrade() -> None:
    _add_column_if_missing("supplier_disputes", sa.Column("expected_quantity", sa.Float(), nullable=True))
    _add_column_if_missing("supplier_disputes", sa.Column("received_quantity", sa.Float(), nullable=True))
    _add_column_if_missing("supplier_disputes", sa.Column("expected_unit_price", sa.Numeric(14, 2), nullable=True))
    _add_column_if_missing("supplier_disputes", sa.Column("invoiced_unit_price", sa.Numeric(14, 2), nullable=True))
    _add_column_if_missing("supplier_disputes", sa.Column("expected_action", sa.String(), nullable=True))
    _add_column_if_missing("supplier_disputes", sa.Column("due_date", sa.DateTime(), nullable=True))
    _add_column_if_missing("supplier_disputes", sa.Column("blocks_receipt", sa.Boolean(), nullable=True, server_default=sa.false()))
    _add_column_if_missing("supplier_disputes", sa.Column("blocks_payment", sa.Boolean(), nullable=True, server_default=sa.false()))
    _add_column_if_missing("supplier_disputes", sa.Column("impact_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    _drop_column_if_present("supplier_disputes", "impact_summary")
    _drop_column_if_present("supplier_disputes", "blocks_payment")
    _drop_column_if_present("supplier_disputes", "blocks_receipt")
    _drop_column_if_present("supplier_disputes", "due_date")
    _drop_column_if_present("supplier_disputes", "expected_action")
    _drop_column_if_present("supplier_disputes", "invoiced_unit_price")
    _drop_column_if_present("supplier_disputes", "expected_unit_price")
    _drop_column_if_present("supplier_disputes", "received_quantity")
    _drop_column_if_present("supplier_disputes", "expected_quantity")

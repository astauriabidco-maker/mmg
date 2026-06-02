"""Add MMG sale order link

Revision ID: d9a8c1f0b6e2
Revises: c2f4b7d9e1a3
Create Date: 2026-06-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d9a8c1f0b6e2"
down_revision: Union[str, Sequence[str], None] = "c2f4b7d9e1a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_NAME = "fk_mmg_dossiers_sale_order_id_sale_orders"


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _columns(table_name: str) -> set[str]:
    inspector = _inspector()
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _foreign_key_names(table_name: str) -> set[str]:
    inspector = _inspector()
    if not inspector.has_table(table_name):
        return set()
    return {fk["name"] for fk in inspector.get_foreign_keys(table_name) if fk["name"]}


def upgrade() -> None:
    """Upgrade schema."""
    mmg_columns = _columns("mmg_dossiers")
    if not mmg_columns:
        return

    if "sale_order_id" not in mmg_columns:
        op.add_column("mmg_dossiers", sa.Column("sale_order_id", sa.Integer(), nullable=True))

    if FK_NAME not in _foreign_key_names("mmg_dossiers"):
        op.create_foreign_key(FK_NAME, "mmg_dossiers", "sale_orders", ["sale_order_id"], ["id"])


def downgrade() -> None:
    """Downgrade schema."""
    if FK_NAME in _foreign_key_names("mmg_dossiers"):
        op.drop_constraint(FK_NAME, "mmg_dossiers", type_="foreignkey")

    if "sale_order_id" in _columns("mmg_dossiers"):
        op.drop_column("mmg_dossiers", "sale_order_id")

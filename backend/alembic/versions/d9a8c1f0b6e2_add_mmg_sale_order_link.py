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

    need_column = "sale_order_id" not in mmg_columns
    need_fk = FK_NAME not in _foreign_key_names("mmg_dossiers")
    if not (need_column or need_fk):
        return

    # batch_alter_table : recopie de table sur SQLite (pas d'ALTER de
    # contrainte), simples ALTER TABLE sur PostgreSQL.
    with op.batch_alter_table("mmg_dossiers") as batch_op:
        if need_column:
            batch_op.add_column(sa.Column("sale_order_id", sa.Integer(), nullable=True))
        if need_fk:
            batch_op.create_foreign_key(FK_NAME, "sale_orders", ["sale_order_id"], ["id"])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("mmg_dossiers") as batch_op:
        if FK_NAME in _foreign_key_names("mmg_dossiers"):
            batch_op.drop_constraint(FK_NAME, type_="foreignkey")

        if "sale_order_id" in _columns("mmg_dossiers"):
            batch_op.drop_column("sale_order_id")

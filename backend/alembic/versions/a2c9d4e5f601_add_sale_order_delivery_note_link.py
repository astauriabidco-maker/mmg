"""add sale order delivery note link

Revision ID: a2c9d4e5f601
Revises: f68a21d4c9b0
Create Date: 2026-07-02 14:05:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a2c9d4e5f601"
down_revision: Union[str, None] = "9f3b6c2d1a40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table : recopie de table sur SQLite (pas d'ALTER de
    # colonne/contrainte), simples ALTER TABLE sur PostgreSQL.
    with op.batch_alter_table("delivery_notes") as batch_op:
        batch_op.add_column(sa.Column("sale_order_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_delivery_notes_sale_order_id_sale_orders",
            "sale_orders",
            ["sale_order_id"],
            ["id"],
        )
        batch_op.alter_column("order_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("delivery_notes") as batch_op:
        batch_op.alter_column("order_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_constraint("fk_delivery_notes_sale_order_id_sale_orders", type_="foreignkey")
        batch_op.drop_column("sale_order_id")

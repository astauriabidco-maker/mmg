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
    op.add_column("delivery_notes", sa.Column("sale_order_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_delivery_notes_sale_order_id_sale_orders",
        "delivery_notes",
        "sale_orders",
        ["sale_order_id"],
        ["id"],
    )
    op.alter_column("delivery_notes", "order_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.alter_column("delivery_notes", "order_id", existing_type=sa.Integer(), nullable=False)
    op.drop_constraint("fk_delivery_notes_sale_order_id_sale_orders", "delivery_notes", type_="foreignkey")
    op.drop_column("delivery_notes", "sale_order_id")

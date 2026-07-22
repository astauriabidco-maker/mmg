"""Add purchase requests

Revision ID: e2f4b6a8c931
Revises: d6f1b8a3c5e9
Create Date: 2026-07-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2f4b6a8c931"
down_revision: Union[str, Sequence[str], None] = "d6f1b8a3c5e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return inspector.has_table(table_name)


def upgrade() -> None:
    if not _has_table("purchase_requests"):
        op.create_table(
            "purchase_requests",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("reference", sa.String(), nullable=True),
            sa.Column("supplier", sa.String(), nullable=True),
            sa.Column("expected_date", sa.DateTime(), nullable=True),
            sa.Column(
                "status",
                sa.Enum(
                    "DRAFT",
                    "PENDING_APPROVAL",
                    "APPROVED",
                    "REJECTED",
                    "CONVERTED",
                    "CANCELLED",
                    name="purchaserequeststatus",
                ),
                nullable=True,
            ),
            sa.Column("total_amount", sa.Numeric(14, 2), nullable=True),
            sa.Column("global_discount_percent", sa.Float(), nullable=True),
            sa.Column("sensitivity_reason", sa.String(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("requested_by", sa.String(), nullable=True),
            sa.Column("approved_by", sa.String(), nullable=True),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("rejected_by", sa.String(), nullable=True),
            sa.Column("rejected_at", sa.DateTime(), nullable=True),
            sa.Column("rejection_reason", sa.Text(), nullable=True),
            sa.Column("converted_by", sa.String(), nullable=True),
            sa.Column("converted_at", sa.DateTime(), nullable=True),
            sa.Column("purchase_order_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_purchase_requests_id"), "purchase_requests", ["id"], unique=False)
        op.create_index(op.f("ix_purchase_requests_reference"), "purchase_requests", ["reference"], unique=True)
        op.create_index(op.f("ix_purchase_requests_purchase_order_id"), "purchase_requests", ["purchase_order_id"], unique=False)

    if not _has_table("purchase_request_lines"):
        op.create_table(
            "purchase_request_lines",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("request_id", sa.Integer(), nullable=True),
            sa.Column("variant_id", sa.Integer(), nullable=True),
            sa.Column("quantity", sa.Float(), nullable=True),
            sa.Column("unit_price", sa.Numeric(14, 2), nullable=True),
            sa.Column("discount_percent", sa.Float(), nullable=True),
            sa.Column("need_priority", sa.String(), nullable=True),
            sa.Column("need_reason", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["request_id"], ["purchase_requests.id"]),
            sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_purchase_request_lines_id"), "purchase_request_lines", ["id"], unique=False)


def downgrade() -> None:
    if _has_table("purchase_request_lines"):
        op.drop_index(op.f("ix_purchase_request_lines_id"), table_name="purchase_request_lines")
        op.drop_table("purchase_request_lines")
    if _has_table("purchase_requests"):
        op.drop_index(op.f("ix_purchase_requests_purchase_order_id"), table_name="purchase_requests")
        op.drop_index(op.f("ix_purchase_requests_reference"), table_name="purchase_requests")
        op.drop_index(op.f("ix_purchase_requests_id"), table_name="purchase_requests")
        op.drop_table("purchase_requests")

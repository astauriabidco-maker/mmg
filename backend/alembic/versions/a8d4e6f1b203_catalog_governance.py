"""Add catalog governance and structured variant attributes

Revision ID: a8d4e6f1b203
Revises: f6a2c4d8e901
Create Date: 2026-07-24 18:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8d4e6f1b203"
down_revision: Union[str, Sequence[str], None] = "f6a2c4d8e901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _columns(table_name: str) -> set[str]:
    if not _inspector().has_table(table_name):
        return set()
    return {column["name"] for column in _inspector().get_columns(table_name)}


def upgrade() -> None:
    variant_columns = _columns("product_variants")
    if _inspector().has_table("product_variants"):
        with op.batch_alter_table("product_variants") as batch_op:
            if "finish" not in variant_columns:
                batch_op.add_column(sa.Column("finish", sa.String(), nullable=True))
            if "conditioning" not in variant_columns:
                batch_op.add_column(sa.Column("conditioning", sa.String(), nullable=True))
            if "units_per_package" not in variant_columns:
                batch_op.add_column(sa.Column("units_per_package", sa.Float(), nullable=True))

    if (
        _inspector().has_table("products")
        and _inspector().has_table("product_variants")
        and not _inspector().has_table("product_audit_logs")
    ):
        op.create_table(
            "product_audit_logs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("variant_id", sa.Integer(), nullable=True),
            sa.Column("action", sa.String(), nullable=False),
            sa.Column("changes", sa.JSON(), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("author", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_product_audit_logs_id", "product_audit_logs", ["id"], unique=False)
        op.create_index("ix_product_audit_logs_product_id", "product_audit_logs", ["product_id"], unique=False)
        op.create_index("ix_product_audit_logs_variant_id", "product_audit_logs", ["variant_id"], unique=False)
        op.create_index("ix_product_audit_logs_action", "product_audit_logs", ["action"], unique=False)
        op.create_index("ix_product_audit_logs_created_at", "product_audit_logs", ["created_at"], unique=False)


def downgrade() -> None:
    if _inspector().has_table("product_audit_logs"):
        op.drop_table("product_audit_logs")
    variant_columns = _columns("product_variants")
    if _inspector().has_table("product_variants"):
        with op.batch_alter_table("product_variants") as batch_op:
            for column_name in ("units_per_package", "conditioning", "finish"):
                if column_name in variant_columns:
                    batch_op.drop_column(column_name)

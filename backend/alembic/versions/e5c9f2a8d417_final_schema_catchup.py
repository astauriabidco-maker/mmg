"""Rattrapage final de schéma : absorbe ensure_schema_compatibility + dérives résiduelles

Revision ID: e5c9f2a8d417
Revises: d1f3a5b7c924
Create Date: 2026-07-03 00:00:00.000000

Cette migration rejoue, de façon idempotente (inspection préalable), les
correctifs que ``models.ensure_schema_compatibility`` appliquait en dur à
chaque démarrage, et comble les dernières dérives constatées entre la chaîne
Alembic et ``Base.metadata.create_all`` :

- tables ``business_rules`` et ``pos_cash_movements`` absentes de la chaîne ;
- colonne ``pos_orders.seller_name`` absente de la chaîne ;
- index ``ix_invoices_invoice_type`` (``index=True`` dans le modèle) jamais
  créé par la migration ``c8f3a21d7b95``.

Après cette migration, Alembic est la source de vérité unique du schéma et
``ensure_schema_compatibility`` est supprimé du code applicatif.

Downgrade volontairement non réversible : sur une base legacy, impossible de
savoir si une colonne/table préexistait à cette migration (c'est précisément
le problème qu'elle résout).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e5c9f2a8d417"
down_revision: Union[str, Sequence[str], None] = "d1f3a5b7c924"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _columns(table_name: str) -> set:
    inspector = _inspector()
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(table_name: str) -> set:
    inspector = _inspector()
    if not inspector.has_table(table_name):
        return set()
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _patch_legacy_columns() -> None:
    """Rejoue les correctifs historiques de ensure_schema_compatibility."""
    product_columns = _columns("products")
    if product_columns:
        if "technical_doc_url" not in product_columns:
            op.add_column("products", sa.Column("technical_doc_url", sa.String(), nullable=True))
        if "compatible_series" not in product_columns:
            op.add_column("products", sa.Column("compatible_series", sa.String(), nullable=True))
        if "catalog_status" not in product_columns:
            op.add_column(
                "products",
                sa.Column("catalog_status", sa.String(), server_default="ACTIVE", nullable=True),
            )
        op.execute(sa.text("UPDATE products SET catalog_status = 'ACTIVE' WHERE catalog_status IS NULL"))

    delivery_columns = _columns("delivery_notes")
    if delivery_columns:
        if "sale_order_id" not in delivery_columns:
            op.add_column("delivery_notes", sa.Column("sale_order_id", sa.Integer(), nullable=True))
            delivery_columns.add("sale_order_id")
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

    order_columns = _columns("orders")
    if order_columns:
        if "sale_order_id" not in order_columns:
            op.add_column("orders", sa.Column("sale_order_id", sa.Integer(), nullable=True))
        if "sale_order_line_id" not in order_columns:
            op.add_column("orders", sa.Column("sale_order_line_id", sa.Integer(), nullable=True))

    sale_columns = _columns("sale_orders")
    if sale_columns:
        if "workflow_type" not in sale_columns:
            op.add_column(
                "sale_orders",
                sa.Column("workflow_type", sa.String(), server_default="FREE_SALE", nullable=True),
            )
        op.execute(sa.text("UPDATE sale_orders SET workflow_type = 'FREE_SALE' WHERE workflow_type IS NULL"))

    sale_line_columns = _columns("sale_order_lines")
    if sale_line_columns:
        if "line_type" not in sale_line_columns:
            op.add_column(
                "sale_order_lines",
                sa.Column("line_type", sa.String(), server_default="SERVICE", nullable=True),
            )
        op.execute(
            sa.text(
                "UPDATE sale_order_lines "
                "SET line_type = CASE WHEN variant_id IS NOT NULL THEN 'STOCK_ITEM' ELSE 'SERVICE' END "
                "WHERE line_type IS NULL OR line_type = ''"
            )
        )

    invoice_columns = _columns("invoices")
    if invoice_columns:
        if "source_invoice_id" not in invoice_columns:
            op.add_column("invoices", sa.Column("source_invoice_id", sa.Integer(), nullable=True))
        if "delivery_note_id" not in invoice_columns:
            op.add_column("invoices", sa.Column("delivery_note_id", sa.Integer(), nullable=True))
        if "return_move_id" not in invoice_columns:
            op.add_column("invoices", sa.Column("return_move_id", sa.Integer(), nullable=True))
        if "invoice_type" not in invoice_columns:
            op.add_column(
                "invoices",
                sa.Column("invoice_type", sa.String(), server_default="FINAL", nullable=True),
            )
        op.execute(sa.text("UPDATE invoices SET invoice_type = 'FINAL' WHERE invoice_type IS NULL OR invoice_type = ''"))
        if "previous_seal" not in invoice_columns:
            op.add_column("invoices", sa.Column("previous_seal", sa.String(), nullable=True))


def _fix_residual_drift() -> None:
    """Comble les écarts résiduels entre la chaîne Alembic et create_all."""
    inspector = _inspector()

    if not inspector.has_table("business_rules"):
        op.create_table(
            "business_rules",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("category", sa.String(), nullable=False),
            sa.Column("rule_key", sa.String(), nullable=False),
            sa.Column("value", sa.String(), nullable=False),
            sa.Column("value_type", sa.String(), nullable=False),
            sa.Column("description", sa.String(), nullable=True),
        )
    if "ix_business_rules_id" not in _index_names("business_rules"):
        op.create_index("ix_business_rules_id", "business_rules", ["id"], unique=False)
    if "ix_business_rules_rule_key" not in _index_names("business_rules"):
        op.create_index("ix_business_rules_rule_key", "business_rules", ["rule_key"], unique=True)

    if not inspector.has_table("pos_cash_movements"):
        op.create_table(
            "pos_cash_movements",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("pos_sessions.id"), nullable=True),
            sa.Column("movement_type", sa.String(), nullable=True),
            sa.Column("amount", sa.Float(), nullable=True),
            sa.Column("reason", sa.String(), nullable=True),
            sa.Column("author", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
    if "ix_pos_cash_movements_id" not in _index_names("pos_cash_movements"):
        op.create_index("ix_pos_cash_movements_id", "pos_cash_movements", ["id"], unique=False)

    if inspector.has_table("pos_orders") and "seller_name" not in _columns("pos_orders"):
        op.add_column("pos_orders", sa.Column("seller_name", sa.String(), server_default="Admin", nullable=True))

    if inspector.has_table("invoices") and "ix_invoices_invoice_type" not in _index_names("invoices"):
        op.create_index("ix_invoices_invoice_type", "invoices", ["invoice_type"], unique=False)


def upgrade() -> None:
    _patch_legacy_columns()
    _fix_residual_drift()


def downgrade() -> None:
    # Migration de rattrapage volontairement non réversible : sur une base
    # legacy, impossible de distinguer ce qui préexistait de ce qui a été
    # ajouté ici (c'est précisément la dérive qu'elle corrige).
    pass

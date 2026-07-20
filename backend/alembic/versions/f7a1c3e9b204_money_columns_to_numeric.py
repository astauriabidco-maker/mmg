"""Montants monétaires Float -> Numeric(14, 2)

Revision ID: f7a1c3e9b204
Revises: e5c9f2a8d417
Create Date: 2026-07-20 00:00:00.000000

Migre les colonnes monétaires (prix, totaux, montants, acomptes, paiements,
fonds de caisse) de ``Float`` vers ``Numeric(14, 2)`` afin d'éliminer les
erreurs d'arrondi comptables du binaire flottant. La précision 14,2 couvre
les montants XAF sans centimes (ordre de grandeur 10^7-10^8) comme l'EUR.

Restent en ``Float`` (légitimes, non monétaires) : quantités, dimensions,
longueurs, seuils de stock, taux de TVA et pourcentages de remise.

Portabilité :
- PostgreSQL (prod) : ``batch_alter_table`` émet de simples
  ``ALTER COLUMN TYPE`` (pas de recréation de table), conversion native
  FLOAT -> NUMERIC.
- SQLite (dev/test) : **no-op documenté** — l'affinité NUMERIC existe déjà
  pour les colonnes FLOAT et SQLAlchemy lie les Decimal côté driver ; aucune
  donnée à convertir. Les bases créées par ``create_all`` (dev, tests)
  obtiennent nativement les colonnes NUMERIC depuis les modèles.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f7a1c3e9b204"
down_revision: Union[str, Sequence[str], None] = "e5c9f2a8d417"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, colonne, nullable) — uniquement les montants monétaires.
MONEY_COLUMNS = [
    ("product_variants", "cost_price", True),
    ("sale_order_lines", "unit_price", True),
    ("pos_sessions", "starting_cash", True),
    ("pos_sessions", "closing_cash", True),
    ("pos_cash_movements", "amount", True),
    ("pos_orders", "amount_total", True),
    ("pos_orders", "amount_paid", True),
    ("pos_orders", "amount_return", True),
    ("pos_order_lines", "unit_price", True),
    ("purchase_orders", "total_amount", True),
    ("purchase_order_lines", "unit_price", True),
    ("supplier_invoices", "subtotal", True),
    ("supplier_invoices", "discount_amount", True),
    ("supplier_invoices", "total_amount", True),
    ("supplier_invoice_lines", "unit_price", True),
    ("supplier_invoice_lines", "line_total", True),
    ("invoices", "subtotal", True),
    ("invoices", "tax_amount", True),
    ("invoices", "total", True),
    ("invoice_lines", "unit_price", True),
    ("payments", "amount", True),
]


def _alter_money_columns(new_type, existing_type) -> None:
    """Altère les colonnes présentes uniquement — idempotent sur les bases
    legacy partielles (tables ou colonnes manquantes : ignorées)."""
    inspector = sa.inspect(op.get_bind())
    existing = {
        table: {column["name"] for column in inspector.get_columns(table)}
        for table in {table for table, _, _ in MONEY_COLUMNS}
        if inspector.has_table(table)
    }
    for table, column, nullable in MONEY_COLUMNS:
        if column not in existing.get(table, set()):
            continue
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(
                column,
                existing_type=existing_type,
                type_=new_type,
                existing_nullable=nullable,
            )


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def upgrade() -> None:
    if _is_sqlite():
        # No-op documenté sur SQLite : l'affinité NUMERIC existe déjà pour les
        # colonnes FLOAT et SQLAlchemy lie les Decimal côté driver ; aucune
        # donnée à convertir. (Le batch mode recréerait les tables et échoue
        # sur les bases legacy partielles dont les FK référencent des tables
        # absentes de la chaîne Alembic.) Le vrai enjeu est PostgreSQL prod.
        return
    _alter_money_columns(sa.Numeric(14, 2), sa.Float())


def downgrade() -> None:
    if _is_sqlite():
        return  # symétrique du upgrade : no-op documenté sur SQLite
    _alter_money_columns(sa.Float(), sa.Numeric(14, 2))

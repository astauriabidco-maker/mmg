"""Unicité des quants (variant_id, location_id) avec dédoublonnage

Revision ID: a4b8c2d6e1f3
Revises: f7a1c3e9b204
Create Date: 2026-07-25 00:00:00.000000

Ajoute la contrainte d'unicité ``uq_stock_quants_variant_location`` sur
``stock_quants (variant_id, location_id)`` : un seul quant par couple
variante/emplacement, ce qui arbitre les créations concurrentes de
``InventoryService.get_or_create_quant``.

Dédoublonnage préalable (données legacy) : les doublons éventuels sont
fusionnés en SOMMANT les quantités sur la ligne conservée (id minimal),
puis les lignes excédentaires sont supprimées — la contrainte ne peut pas
être créée sinon.

Idempotent :
- le dédoublonnage est rejouable sans effet sur des données déjà propres ;
- la création de la contrainte est ignorée si elle existe déjà (inspection
  préalable), y compris sur les bases créées par ``create_all`` depuis les
  modèles à jour.

Portabilité : ``batch_alter_table`` recrée la table sous SQLite (qui ne
supporte pas ``ADD CONSTRAINT``) et émet un simple ``ALTER TABLE`` sous
PostgreSQL.
"""
from typing import Optional, Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a4b8c2d6e1f3"
down_revision: Union[str, Sequence[str], None] = "f7a1c3e9b204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONSTRAINT_NAME = "uq_stock_quants_variant_location"


def _table_exists() -> bool:
    return sa.inspect(op.get_bind()).has_table("stock_quants")


def _constraint_exists() -> bool:
    return _constraint_name() is not None


def _constraint_name() -> Optional[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("stock_quants"):
        return None
    uniques = inspector.get_unique_constraints("stock_quants")
    for unique in uniques:
        if unique.get("name") == CONSTRAINT_NAME:
            return CONSTRAINT_NAME
        # Détection par colonnes : une contrainte équivalente non nommée
        # (base legacy) rend aussi la création inutile/impossible.
        if list(unique.get("column_names") or []) == ["variant_id", "location_id"]:
            return unique.get("name")
    return None


def _merge_duplicate_quants() -> None:
    # 1) La ligne conservée (id minimal par couple) absorbe la somme des
    #    quantités de tous ses doublons.
    op.execute(
        sa.text(
            """
            UPDATE stock_quants
            SET quantity = (
                SELECT COALESCE(SUM(sq2.quantity), 0)
                FROM stock_quants sq2
                WHERE sq2.variant_id = stock_quants.variant_id
                  AND sq2.location_id = stock_quants.location_id
            )
            """
        )
    )
    # 2) Suppression des lignes excédentaires (toutes sauf l'id minimal).
    op.execute(
        sa.text(
            """
            DELETE FROM stock_quants
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM stock_quants
                GROUP BY variant_id, location_id
            )
            """
        )
    )


def upgrade() -> None:
    # Bases legacy partielles (ex. test_schema_compatibility) : rien à faire
    # si la table n'existe pas — le modèle la créera avec la contrainte.
    if not _table_exists() or _constraint_exists():
        return
    _merge_duplicate_quants()
    with op.batch_alter_table("stock_quants") as batch_op:
        batch_op.create_unique_constraint(CONSTRAINT_NAME, ["variant_id", "location_id"])


def downgrade() -> None:
    if not _table_exists():
        return
    name = _constraint_name()
    if not name:
        return
    with op.batch_alter_table("stock_quants") as batch_op:
        batch_op.drop_constraint(name, type_="unique")

"""Persistance de la configuration fine des dossiers MMG

Revision ID: d6f1b8a3c5e9
Revises: b7e2f1a9c3d5
Create Date: 2026-08-02 00:00:00.000000

Ajoute ``mmg_dossiers.configuration`` (JSON, nullable) : payload de
configuration du formulaire de métré (forme, ventilation, soubassement_type,
doublage...) incluant la sous-clé ``annexes`` (volets, moustiquaire, frais de
pose, livraison). Cette colonne alimente la logique de plus-values de
``POST /v2/mmg/{id}/send-quote``.

Idempotent : ajout ignoré si la colonne existe déjà (bases créées par
``create_all`` depuis les modèles à jour).

Portabilité : ``batch_alter_table`` recrée la table sous SQLite et émet un
simple ``ALTER TABLE`` sous PostgreSQL ; le type ``JSON`` SQLAlchemy est
portable sur les deux dialectes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d6f1b8a3c5e9"
down_revision: Union[str, Sequence[str], None] = "b7e2f1a9c3d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "mmg_dossiers"
COLUMN_NAME = "configuration"


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _columns(TABLE_NAME)
    if not columns:
        # Bases legacy partielles : le modèle créera la table avec la colonne.
        return
    if COLUMN_NAME not in columns:
        with op.batch_alter_table(TABLE_NAME) as batch_op:
            batch_op.add_column(sa.Column(COLUMN_NAME, sa.JSON(), nullable=True))


def downgrade() -> None:
    columns = _columns(TABLE_NAME)
    if not columns:
        return
    if COLUMN_NAME in columns:
        with op.batch_alter_table(TABLE_NAME) as batch_op:
            batch_op.drop_column(COLUMN_NAME)

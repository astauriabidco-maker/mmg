"""Persistance de la signature client sur les bons de livraison

Revision ID: b7e2f1a9c3d5
Revises: c6e1a8d3f045
Create Date: 2026-08-01 00:00:00.000000

Ajoute ``delivery_notes.signature_path`` (String, nullable) : chemin relatif
sous ``uploads/`` du fichier image de la signature client capturée à la
livraison (endpoint ``POST /v2/logistics/notes/{id}/deliver``).

Idempotent : ajout ignoré si la colonne existe déjà (bases créées par
``create_all`` depuis les modèles à jour).

Portabilité : ``batch_alter_table`` recrée la table sous SQLite et émet un
simple ``ALTER TABLE`` sous PostgreSQL.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7e2f1a9c3d5"
down_revision: Union[str, Sequence[str], None] = "c6e1a8d3f045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "delivery_notes"
COLUMN_NAME = "signature_path"


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
            batch_op.add_column(sa.Column(COLUMN_NAME, sa.String(), nullable=True))


def downgrade() -> None:
    columns = _columns(TABLE_NAME)
    if not columns:
        return
    if COLUMN_NAME in columns:
        with op.batch_alter_table(TABLE_NAME) as batch_op:
            batch_op.drop_column(COLUMN_NAME)

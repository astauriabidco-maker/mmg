"""Comptage aveugle sur les campagnes d'inventaire physique

Revision ID: b5c9d3e7f2a1
Revises: a4b8c2d6e1f3
Create Date: 2026-07-26 00:00:00.000000

Ajoute la colonne ``blind_counting`` (Boolean, défaut False) sur
``inventory_sessions`` : quand elle est active, l'API masque
``expected_quantity``/``variance_quantity`` des lignes de comptage jusqu'à la
validation (les écarts restent calculés côté serveur).

Idempotent : la création de la colonne est ignorée si elle existe déjà
(inspection préalable), y compris sur les bases créées par ``create_all``
depuis les modèles à jour.

Portabilité : ``batch_alter_table`` recrée la table sous SQLite et émet un
simple ``ALTER TABLE`` sous PostgreSQL.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b5c9d3e7f2a1"
down_revision: Union[str, Sequence[str], None] = "a4b8c2d6e1f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "inventory_sessions"
COLUMN_NAME = "blind_counting"


def _column_exists() -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(TABLE_NAME):
        return False
    return any(column["name"] == COLUMN_NAME for column in inspector.get_columns(TABLE_NAME))


def upgrade() -> None:
    # Bases legacy partielles : rien à faire si la table n'existe pas — le
    # modèle la créera avec la colonne.
    if _column_exists():
        return
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(TABLE_NAME):
        return
    with op.batch_alter_table(TABLE_NAME) as batch_op:
        batch_op.add_column(
            sa.Column(COLUMN_NAME, sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    if not _column_exists():
        return
    with op.batch_alter_table(TABLE_NAME) as batch_op:
        batch_op.drop_column(COLUMN_NAME)

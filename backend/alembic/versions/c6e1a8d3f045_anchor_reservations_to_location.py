"""Ancrage des réservations de stock sur un emplacement interne

Revision ID: c6e1a8d3f045
Revises: b5c9d3e7f2a1
Create Date: 2026-07-28 00:00:00.000000

Ajoute ``stock_reservations.location_id`` (FK ``stock_locations``) : la
réservation devient « ferme » sur un emplacement — le disponible est calculé
sur cet emplacement et la consommation y puise, avec re-contrôle au débit.

Backfill des réservations existantes : convention historique du débit atelier
= l'emplacement interne actif nommé « WH/Stock » (source en dur avant cette
révision). À défaut, on prend le premier emplacement interne actif (id le
plus bas). Sans aucun emplacement interne actif, la colonne reste NULL et le
code retombe sur le comportement précédent (emplacement par défaut à la
consommation).

Idempotent : ajout ignoré si la colonne existe déjà (bases créées par
``create_all`` depuis les modèles à jour).

Portabilité : ``batch_alter_table`` recrée la table sous SQLite et émet de
simples ``ALTER TABLE`` sous PostgreSQL.
"""
from typing import Optional, Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c6e1a8d3f045"
down_revision: Union[str, Sequence[str], None] = "b5c9d3e7f2a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "stock_reservations"
COLUMN_NAME = "location_id"
FK_NAME = "fk_stock_reservations_location_id_stock_locations"
INDEX_NAME = "ix_stock_reservations_location_id"
DEFAULT_INTERNAL_LOCATION_NAME = "WH/Stock"


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _foreign_key_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {fk["name"] for fk in inspector.get_foreign_keys(table_name) if fk["name"]}


def _index_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _main_internal_location_id() -> Optional[int]:
    """Emplacement interne principal : « WH/Stock » actif, sinon premier interne actif."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("stock_locations"):
        return None
    locations = sa.table(
        "stock_locations",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("usage", sa.String),
        sa.column("is_active", sa.Boolean),
    )
    base_filter = sa.and_(locations.c.usage == "internal", locations.c.is_active == sa.true())
    location_id = bind.execute(
        sa.select(locations.c.id)
        .where(base_filter, locations.c.name == DEFAULT_INTERNAL_LOCATION_NAME)
        .order_by(locations.c.id)
        .limit(1)
    ).scalar()
    if location_id is None:
        location_id = bind.execute(
            sa.select(locations.c.id).where(base_filter).order_by(locations.c.id).limit(1)
        ).scalar()
    return location_id


def upgrade() -> None:
    columns = _columns(TABLE_NAME)
    if not columns:
        # Bases legacy partielles : le modèle créera la table avec la colonne.
        return
    fk_names = _foreign_key_names(TABLE_NAME)

    if COLUMN_NAME not in columns or FK_NAME not in fk_names:
        with op.batch_alter_table(TABLE_NAME) as batch_op:
            if COLUMN_NAME not in columns:
                batch_op.add_column(sa.Column(COLUMN_NAME, sa.Integer(), nullable=True))
            if FK_NAME not in fk_names:
                batch_op.create_foreign_key(FK_NAME, "stock_locations", [COLUMN_NAME], ["id"])

    if INDEX_NAME not in _index_names(TABLE_NAME):
        op.create_index(INDEX_NAME, TABLE_NAME, [COLUMN_NAME], unique=False)

    # Backfill : ancrer les réservations existantes sur l'emplacement interne
    # principal (convention historique « WH/Stock » du débit atelier).
    main_location_id = _main_internal_location_id()
    if main_location_id is not None:
        reservations = sa.table(TABLE_NAME, sa.column(COLUMN_NAME, sa.Integer))
        op.get_bind().execute(
            reservations.update()
            .where(reservations.c.location_id.is_(None))
            .values(location_id=main_location_id)
        )


def downgrade() -> None:
    columns = _columns(TABLE_NAME)
    if not columns:
        return
    fk_names = _foreign_key_names(TABLE_NAME)

    if INDEX_NAME in _index_names(TABLE_NAME):
        op.drop_index(INDEX_NAME, table_name=TABLE_NAME)

    with op.batch_alter_table(TABLE_NAME) as batch_op:
        if FK_NAME in fk_names:
            batch_op.drop_constraint(FK_NAME, type_="foreignkey")
        if COLUMN_NAME in columns:
            batch_op.drop_column(COLUMN_NAME)

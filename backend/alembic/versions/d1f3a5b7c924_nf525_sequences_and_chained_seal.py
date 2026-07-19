"""nf525: sequences de numerotation transactionnelles + sceau chaine

Revision ID: d1f3a5b7c924
Revises: 7c9d1e4a5b28
Create Date: 2026-07-18 09:00:00.000000

- Cree la table `document_sequences` (compteurs atomiques par type de piece
  et par annee) remplaçant les anciens COUNT+1 non transactionnels.
- Ajoute `invoices.previous_seal` pour le chainage du sceau NF525
  (HMAC-SHA256 : chaque piece scelle le sceau de la precedente).
- Initialise les compteurs a partir des references existantes (MAX du
  suffixe numerique par prefixe/annee) afin de ne jamais reemettre un
  numero deja consomme.

Donnees existantes : les pieces deja scellees avec l'ancien SHA-256 (sans
cle, incluant le status mutable) conservent leur sceau « legacy » tel quel —
elles ne sont pas re-scellees, car re-sceller reviendrait a alterer des
pieces deja emises. La nouvelle chaine HMAC s'ancre sur le dernier sceau
existant (legacy ou non) via `previous_seal`.
"""

from typing import Sequence, Union
import re

from alembic import op
import sqlalchemy as sa


revision: str = "d1f3a5b7c924"
down_revision: Union[str, Sequence[str], None] = "7c9d1e4a5b28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# doc_kind -> (table, colonne reference, prefixe)
SEED_SOURCES = {
    "invoice": ("invoices", "reference", "F"),
    "credit_note": ("invoices", "reference", "AV"),
    "quote": ("sale_orders", "reference", "DEV"),
    "purchase_order": ("purchase_orders", "reference", "PO"),
    "supplier_invoice": ("supplier_invoices", "reference", "FF"),
    "delivery_note": ("delivery_notes", "reference", "BL"),
    "mmg": ("mmg_dossiers", "reference", "MMG"),
}


def _has_table(inspector: sa.engine.reflection.Inspector, table_name: str) -> bool:
    return inspector.has_table(table_name)


def _columns(inspector: sa.engine.reflection.Inspector, table_name: str) -> set:
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _existing_maxima(bind, table: str, column: str, prefix: str) -> dict:
    """MAX du suffixe numerique par annee pour un prefixe donne.

    Seules les references au format strict PREFIX-AAAA-N+ sont prises en
    compte : les anciens devis `DEV-AAAA-MM-JJ-HHMM` (format date-minute,
    sans compteur) sont ignores et ne faussent pas la sequence.
    """
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d{{4}})-(\d+)$")
    rows = bind.execute(
        sa.text(f"SELECT {column} FROM {table} WHERE {column} LIKE :like_pattern"),
        {"like_pattern": f"{prefix}-%"},
    )
    maxima: dict = {}
    for (reference,) in rows:
        match = pattern.match(reference or "")
        if not match:
            continue
        year, number = int(match.group(1)), int(match.group(2))
        maxima[year] = max(maxima.get(year, 0), number)
    return maxima


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "document_sequences"):
        op.create_table(
            "document_sequences",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("doc_kind", sa.String(), nullable=False),
            sa.Column("year", sa.Integer(), nullable=False),
            sa.Column("counter", sa.Integer(), nullable=False, server_default="0"),
            sa.UniqueConstraint("doc_kind", "year", name="uq_document_sequences_kind_year"),
        )

    if _has_table(inspector, "invoices") and "previous_seal" not in _columns(inspector, "invoices"):
        op.add_column("invoices", sa.Column("previous_seal", sa.String(), nullable=True))

    # Initialisation des compteurs a partir des donnees existantes : on ne
    # reemet jamais un numero deja consomme (la base de dev contient
    # notamment 2 factures de demonstration).
    for doc_kind, (table, column, prefix) in SEED_SOURCES.items():
        if not _has_table(inspector, table):
            continue
        for year, maximum in _existing_maxima(bind, table, column, prefix).items():
            already_seeded = bind.execute(
                sa.text(
                    "SELECT 1 FROM document_sequences "
                    "WHERE doc_kind = :doc_kind AND year = :year"
                ),
                {"doc_kind": doc_kind, "year": year},
            ).first()
            if not already_seeded:
                bind.execute(
                    sa.text(
                        "INSERT INTO document_sequences (doc_kind, year, counter) "
                        "VALUES (:doc_kind, :year, :counter)"
                    ),
                    {"doc_kind": doc_kind, "year": year, "counter": maximum},
                )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "previous_seal" in _columns(inspector, "invoices"):
        op.drop_column("invoices", "previous_seal")
    if _has_table(inspector, "document_sequences"):
        op.drop_table("document_sequences")

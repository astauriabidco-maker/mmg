"""Numérotation transactionnelle des pièces commerciales (NF525).

Remplace les anciens `COUNT + 1` (race condition sous concurrence, séquence
altérable) par une table `document_sequences` incrémentée atomiquement :

- la ligne (doc_kind, année) est verrouillée via `SELECT ... FOR UPDATE`
  (`with_for_update()`) dans la transaction courante. Sur PostgreSQL c'est un
  vrai verrou de ligne ; sur SQLite la clause est ignorée mais l'écriture est
  déjà sérialisée par le verrou base de la transaction en cours ;
- la création concurrente de la ligne de séquence (première pièce d'un type
  pour une année) est arbitrée par la contrainte d'unicité
  `uq_document_sequences_kind_year` : le perdant repart sur un
  `SELECT ... FOR UPDATE` après rollback au savepoint.

Usage : ``next_number(db, "invoice")`` -> ``"F-2026-0001"``.
"""
from datetime import datetime
from typing import Optional
import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models
from ..core.time import utcnow

# doc_kind -> (préfixe de référence, largeur du compteur)
DOC_KIND_FORMATS = {
    "invoice": ("F", 4),           # Factures :          F-YYYY-XXXX
    "credit_note": ("AV", 4),      # Avoirs :            AV-YYYY-XXXX
    "quote": ("DEV", 4),           # Devis :             DEV-YYYY-XXXX
    "purchase_request": ("PR", 4), # Demandes d'achat :  PR-YYYY-XXXX
    "purchase_order": ("PO", 4),   # Commandes fourn.:   PO-YYYY-XXXX
    "supplier_invoice": ("FF", 4), # Factures fourn.:    FF-YYYY-XXXX
    "delivery_note": ("BL", 4),    # Bons de livraison : BL-YYYY-XXXX
    "mmg": ("MMG", 5),             # Dossiers MMG :      MMG-YYYY-XXXXX
}

# doc_kind -> modèle portant la colonne `reference` (auto-amorçage du compteur)
DOC_KIND_MODELS = {
    "invoice": models.Invoice,
    "credit_note": models.Invoice,
    "quote": models.SaleOrder,
    "purchase_request": models.PurchaseRequest,
    "purchase_order": models.PurchaseOrder,
    "supplier_invoice": models.SupplierInvoice,
    "delivery_note": models.DeliveryNote,
    "mmg": models.MMG,
}


def next_number(db: Session, doc_kind: str, year: Optional[int] = None) -> str:
    """Retourne la prochaine référence pour ``doc_kind`` (transaction courante).

    Le compteur est incrémenté ici mais n'est définitivement consommé qu'au
    commit de la transaction appelante : un numéro émis n'est jamais réémis,
    même en cas d'exécutions concurrentes.
    """
    if doc_kind not in DOC_KIND_FORMATS:
        raise ValueError(f"Type de document inconnu: {doc_kind!r}")
    prefix, padding = DOC_KIND_FORMATS[doc_kind]
    year = year or utcnow().year

    sequence = _locked_sequence(db, doc_kind, year)
    sequence.counter = int(sequence.counter or 0) + 1
    db.flush()

    return f"{prefix}-{year}-{sequence.counter:0{padding}d}"


def _locked_sequence(db: Session, doc_kind: str, year: int) -> models.DocumentSequence:
    sequence = (
        db.query(models.DocumentSequence)
        .filter(
            models.DocumentSequence.doc_kind == doc_kind,
            models.DocumentSequence.year == year,
        )
        .with_for_update()
        .first()
    )
    if sequence is not None:
        return sequence

    # Première pièce de ce type pour l'année : création de la ligne de
    # séquence, amorcée sur le MAX des références déjà présentes (bases sans
    # migration Alembic, données legacy) pour ne jamais réémettre un numéro.
    # En cas de création concurrente, la contrainte d'unicité départage ;
    # le perdant reverrouille la ligne gagnante.
    sequence = models.DocumentSequence(
        doc_kind=doc_kind,
        year=year,
        counter=_existing_max_counter(db, doc_kind, year),
    )
    db.add(sequence)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        db.expunge(sequence)
        sequence = (
            db.query(models.DocumentSequence)
            .filter(
                models.DocumentSequence.doc_kind == doc_kind,
                models.DocumentSequence.year == year,
            )
            .with_for_update()
            .first()
        )
        if sequence is None:  # défensif : la contrainte garantit son existence
            raise
    return sequence


def _existing_max_counter(db: Session, doc_kind: str, year: int) -> int:
    """MAX du suffixe numérique déjà émis pour (doc_kind, année).

    Seules les références au format strict PREFIXE-AAAA-N+ comptent : les
    anciens devis `DEV-AAAA-MM-JJ-HHMM` (format date-minute) sont ignorés.
    """
    prefix, _padding = DOC_KIND_FORMATS[doc_kind]
    model = DOC_KIND_MODELS[doc_kind]
    pattern = re.compile(rf"^{re.escape(prefix)}-{year}-(\d+)$")
    references = db.query(model.reference).filter(model.reference.like(f"{prefix}-{year}-%")).all()
    maximum = 0
    for (reference,) in references:
        match = pattern.match(reference or "")
        if match:
            maximum = max(maximum, int(match.group(1)))
    return maximum

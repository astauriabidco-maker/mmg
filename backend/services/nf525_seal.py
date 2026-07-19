"""Sceau anti-fraude NF525 : HMAC-SHA256 à clé secrète, chaîné entre pièces.

Différences avec l'ancien « sceau » (SHA-256 simple, recalculable par tous) :

- **Clé secrète** : le sceau est un HMAC-SHA256. La clé vient de la variable
  d'environnement ``NF525_HMAC_KEY`` ; à défaut, repli documenté sur
  ``SECRET_KEY`` (un warning est émis au premier usage — à corriger en
  production).
- **Champs immuables uniquement** : le payload scellé contient la référence,
  le client (nom + SIRET), la date d'émission et les montants (HT, TVA, TTC).
  Le ``status`` (mutable : UNPAID -> PARTIAL -> PAID) en est exclu — un
  encaissement ne change plus jamais le sceau.
- **Chaînage** : chaque sceau intègre le sceau de la pièce (facture ou avoir)
  précédente, mémorisé dans ``invoices.previous_seal``. La première pièce
  scellée utilise la chaîne vide ``GENESIS_SEAL`` comme amorce (genesis).

Les pièces historiques scellées avec l'ancien SHA-256 conservent leur sceau
« legacy » ; la nouvelle chaîne s'ancre sur le dernier sceau existant.
"""
import hashlib
import hmac
import logging
import os

from sqlalchemy.orm import Session

from .. import models

logger = logging.getLogger(__name__)

# Amorce de chaîne pour la toute première pièce scellée (genesis documentée).
GENESIS_SEAL = ""

_fallback_warning_emitted = False


def _hmac_key() -> bytes:
    """Clé HMAC : NF525_HMAC_KEY, sinon repli documenté sur SECRET_KEY."""
    global _fallback_warning_emitted
    key = os.environ.get("NF525_HMAC_KEY")
    if key:
        return key.encode("utf-8")

    if not _fallback_warning_emitted:
        logger.warning(
            "NF525_HMAC_KEY non définie : le sceau NF525 utilise SECRET_KEY en repli. "
            "Définir NF525_HMAC_KEY avec une clé dédiée en production."
        )
        _fallback_warning_emitted = True

    from ..core import security  # import tardif pour éviter les cycles

    return security.SECRET_KEY.encode("utf-8")


def seal_payload(invoice: models.Invoice, previous_seal: str) -> str:
    """Payload scellé : chaînage + données immuables de la pièce (sans status)."""
    issue_date = invoice.issue_date.isoformat() if invoice.issue_date else ""
    parts = [
        previous_seal or GENESIS_SEAL,
        invoice.reference or "",
        invoice.client_name or "",
        invoice.client_siret or "",
        issue_date,
        f"{float(invoice.subtotal or 0):.2f}",
        f"{float(invoice.tax_amount or 0):.2f}",
        f"{float(invoice.total or 0):.2f}",
    ]
    return "|".join(parts)


def compute_seal(invoice: models.Invoice, previous_seal: str = GENESIS_SEAL) -> str:
    """HMAC-SHA256 du payload — vérifiable uniquement avec la clé secrète."""
    payload = seal_payload(invoice, previous_seal)
    return hmac.new(_hmac_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def last_seal(db: Session) -> str:
    """Sceau de la dernière pièce scellée (ordre d'émission = id croissant)."""
    last = (
        db.query(models.Invoice)
        .filter(models.Invoice.qr_code_hash.isnot(None))
        .order_by(models.Invoice.id.desc())
        .first()
    )
    return last.qr_code_hash if last else GENESIS_SEAL


def seal_invoice(db: Session, invoice: models.Invoice) -> str:
    """Scelle une pièce et la chaîne à la précédente.

    À appeler après ``db.flush()`` de la pièce (les montants et la référence
    doivent être définitifs). Le sceau ne doit jamais être recalculé ensuite :
    il est immuable, conformément à l'exigence d'inaltérabilité NF525.
    """
    previous = last_seal(db)
    invoice.previous_seal = previous
    invoice.qr_code_hash = compute_seal(invoice, previous)
    return invoice.qr_code_hash

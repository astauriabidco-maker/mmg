"""Helpers horaires centralisés.

Les colonnes ``DateTime`` du schéma sont **naïves** (sans timezone) et les
données historiques sont stockées en UTC naïf (``datetime.utcnow()``,
déprécié depuis Python 3.12). Pour rester compatible avec le schéma et les
données existantes — y compris les sceaux NF525 qui sérialisent
``issue_date.isoformat()`` — on conserve la convention « naïf UTC » partout.

Utiliser :func:`utcnow` à la place de ``datetime.utcnow``.
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Horodatage UTC courant, naïf (sans tzinfo), compatible avec les
    colonnes ``DateTime`` existantes et les données historiques."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

"""Tests de la migration des montants monétaires Float -> Numeric(14, 2).

Garantit que :
- les colonnes monétaires sont bien en ``Numeric`` dans les modèles ;
- un montant à 2 décimales fait un aller-retour exact (pas d'arrondi binaire) ;
- le payload du sceau NF525 est identique que la valeur soit un ``Decimal``
  (lecture ORM) ou un ``float`` (sceaux historiques) — inaltérabilité des
  sceaux existants.
"""
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend import models
from backend.services import nf525_seal


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def test_money_columns_are_numeric():
    """Les colonnes monétaires clés sont en Numeric(14, 2), pas en Float."""
    from sqlalchemy import Numeric

    money_columns = [
        (models.Invoice.subtotal, "invoices.subtotal"),
        (models.Invoice.tax_amount, "invoices.tax_amount"),
        (models.Invoice.total, "invoices.total"),
        (models.InvoiceLine.unit_price, "invoice_lines.unit_price"),
        (models.Payment.amount, "payments.amount"),
        (models.SaleOrderLine.unit_price, "sale_order_lines.unit_price"),
        (models.POSOrder.amount_total, "pos_orders.amount_total"),
        (models.PurchaseOrder.total_amount, "purchase_orders.total_amount"),
        (models.ProductVariant.cost_price, "product_variants.cost_price"),
    ]
    for column, label in money_columns:
        assert isinstance(column.type, Numeric), f"{label} devrait être Numeric"
        assert column.type.scale == 2, f"{label} devrait avoir 2 décimales"


def test_two_decimal_amount_roundtrip_is_exact():
    """Un montant à 2 décimales est relu exactement (Decimal), sans arrondi
    binaire de type 0.1 + 0.2 = 0.30000000000000004."""
    db = _session()
    try:
        invoice = models.Invoice(
            reference="F-2099-0001",
            client_name="Client Arrondi",
            due_date=datetime(2099, 1, 1),
            status="UNPAID",
            subtotal=Decimal("0.1") + Decimal("0.2"),
            tax_amount=Decimal("0.06"),
            total=Decimal("0.36"),
        )
        db.add(invoice)
        db.commit()
        db.expire_all()

        reloaded = db.query(models.Invoice).filter_by(reference="F-2099-0001").one()
        assert reloaded.subtotal == Decimal("0.30")
        assert reloaded.tax_amount == Decimal("0.06")
        assert reloaded.total == Decimal("0.36")

        payment = models.Payment(invoice_id=reloaded.id, amount=Decimal("0.36"), method="CB")
        db.add(payment)
        db.commit()
        db.expire_all()
        reloaded_payment = db.query(models.Payment).one()
        assert reloaded_payment.amount == Decimal("0.36")
    finally:
        db.close()


def test_nf525_seal_format_stable_with_decimal():
    """Le payload scellé est identique que les montants soient Decimal ou float.

    Critique : les sceaux des pièces existantes (calculés sur des Float) ne
    doivent pas changer après la migration Numeric.
    """
    issue_date = datetime(2026, 7, 20, 10, 30, 0)
    base = dict(
        reference="F-2026-0001",
        client_name="Client Sceau",
        client_siret="12345678900011",
        issue_date=issue_date,
    )
    as_float = SimpleNamespace(**base, subtotal=100.10, tax_amount=20.02, total=120.12)
    as_decimal = SimpleNamespace(
        **base,
        subtotal=Decimal("100.10"),
        tax_amount=Decimal("20.02"),
        total=Decimal("120.12"),
    )
    assert nf525_seal.seal_payload(as_float, "amorce") == nf525_seal.seal_payload(as_decimal, "amorce")
    assert nf525_seal.compute_seal(as_float, "") == nf525_seal.compute_seal(as_decimal, "")

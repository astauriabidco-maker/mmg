"""Derived receivables only: never change fiscal documents or record cash flows."""
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, or_

from .. import models, schemas


def money(value):
    return Decimal(str(value or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def is_credit_note(invoice):
    return invoice.status == 'AVOIR' or invoice.invoice_type == 'CREDIT_NOTE'


def linked_credit_totals(db, invoice_ids):
    """Signed sums of issued negative credit notes, keyed by source invoice ID."""
    if not invoice_ids:
        return {}
    return dict(db.query(models.Invoice.source_invoice_id, func.sum(models.Invoice.total))
                .filter(models.Invoice.source_invoice_id.in_(invoice_ids),
                        or_(models.Invoice.status == 'AVOIR', models.Invoice.invoice_type == 'CREDIT_NOTE'),
                        models.Invoice.status.notin_(['DRAFT', 'CANCELLED', 'VOID']),
                        models.Invoice.total < 0)
                .group_by(models.Invoice.source_invoice_id).all())


def invoice_balance(invoice, linked_total=0):
    """Return Decimal amounts and action flags without mutating the ORM invoice.

    customer_credit is the credit balance after real payments; refund_due is
    its cash-backed portion, pending a separate, explicit refund workflow.
    A partially credited invoice can still have a collectible balance.
    """
    paid = sum((money(p.amount) for p in invoice.payments), Decimal('0.00'))
    credit = -min(money(linked_total), Decimal('0.00'))
    note = is_credit_note(invoice)
    net = money(invoice.total) - credit
    balance = net - paid
    customer_credit = max(-balance, Decimal('0.00')) if not note else Decimal('0.00')
    credited = credit > 0 and not note
    actionable = not note and invoice.status not in ('DRAFT', 'CANCELLED', 'VOID', 'PAID') and balance > 0
    status = ('AVOIR' if note else
              'CREDITED' if credited and net <= 0 else
              'PARTIALLY_CREDITED' if credited else invoice.status)
    return dict(total_paid=paid, credit_notes_total=credit, net_total=net,
                balance_due=max(balance, Decimal('0.00')) if not note else Decimal('0.00'),
                customer_credit=customer_credit,
                refund_due=min(customer_credit, max(paid, Decimal('0.00'))),
                is_credited=credited, accounting_status=status,
                can_pay=actionable, can_remind=actionable,
                can_credit=not note and invoice.status not in ('DRAFT', 'CANCELLED', 'VOID') and net > 0)


def invoice_response(db, invoice, credit_totals=None):
    if credit_totals is None:
        credit_totals = linked_credit_totals(db, [invoice.id])
    values = invoice_balance(invoice, credit_totals.get(invoice.id, 0))
    # Validate the calculated fields too, so Decimal amounts serialize as numbers.
    return schemas.InvoiceResponse.model_validate({
        **schemas.InvoiceResponse.model_validate(invoice).model_dump(), **values,
    })

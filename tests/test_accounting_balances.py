"""Linked credit notes affect receivables, never fiscal originals or cash flows."""
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend import models
from backend.core.security import get_password_hash
from backend.services.accounting import invoice_balance


@pytest.fixture()
def accounting_client(isolated_client, monkeypatch):
    monkeypatch.setenv('NF525_HMAC_KEY', 'accounting-regression-key')
    client, sessions = isolated_client
    with sessions() as db:
        db.add(models.User(username='accountant', pin_hash=get_password_hash('1234'),
                           role='ADMIN', is_active=True))
        db.commit()
    token = client.post('/token', data={'username': 'accountant', 'password': '1234'})
    assert token.status_code == 200
    return client, sessions, {'Authorization': f"Bearer {token.json()['access_token']}"}


def seed(sessions, paid=40, credits=(-120,)):
    with sessions() as db:
        invoice = models.Invoice(reference='F-2026-0008', client_name='Préprod',
                                 due_date=datetime(2026, 12, 1), status='PARTIAL' if paid else 'UNPAID',
                                 subtotal=100, tax_amount=20, total=120,
                                 qr_code_hash='original-seal', previous_seal='previous-seal')
        db.add(invoice)
        db.flush()
        if paid:
            db.add(models.Payment(invoice_id=invoice.id, amount=paid, method='CB'))
        for index, total in enumerate(credits):
            db.add(models.Invoice(reference=f'AV-2026-{index + 2:04}', client_name='Préprod',
                                  source_invoice_id=invoice.id, status='AVOIR', invoice_type='CREDIT_NOTE',
                                  total=total, subtotal=Decimal(str(total)) / Decimal('1.2'),
                                  tax_amount=0, due_date=datetime(2026, 12, 1)))
        db.commit()
        return invoice.id


def listed(client, headers, invoice_id):
    response = client.get('/v2/accounting/invoices', headers=headers)
    assert response.status_code == 200, response.text
    return next(item for item in response.json() if item['id'] == invoice_id)


@pytest.mark.parametrize('paid,credits,due,credit,status', [
    (40, (-120,), 0, 40, 'CREDITED'),
    (0, (-120,), 0, 0, 'CREDITED'),
    (120, (-120,), 0, 120, 'CREDITED'),
    (40, (-30, -30), 20, 0, 'PARTIALLY_CREDITED'),
    (100, (-60,), 0, 40, 'PARTIALLY_CREDITED'),
])
def test_historical_linked_credits(accounting_client, paid, credits, due, credit, status):
    client, sessions, headers = accounting_client
    invoice_id = seed(sessions, paid, credits)
    invoice = listed(client, headers, invoice_id)
    assert invoice['balance_due'] == due
    assert invoice['customer_credit'] == credit
    assert invoice['refund_due'] == credit
    assert invoice['credit_notes_total'] == -sum(credits)
    assert invoice['net_total'] == 120 + sum(credits)
    assert invoice['total_paid'] == paid
    assert invoice['is_credited'] is True
    assert invoice['accounting_status'] == status
    assert invoice['can_pay'] == (due > 0)
    assert invoice['can_remind'] == (due > 0)
    assert invoice['can_credit'] == (120 + sum(credits) > 0)
    if due == 0:
        for endpoint, payload in [('pay', {'amount': 1, 'method': 'CB'}), ('remind', None)]:
            response = client.post(f'/v2/accounting/invoices/{invoice_id}/{endpoint}', headers=headers, json=payload)
            assert response.status_code == 400, response.text
    with sessions() as db:
        original = db.get(models.Invoice, invoice_id)
        assert original.total == 120
        assert original.status == ('PARTIAL' if paid else 'UNPAID')
        assert original.qr_code_hash == 'original-seal'
        assert original.previous_seal == 'previous-seal'
        assert db.query(models.Payment).count() == (1 if paid else 0)
        assert db.query(models.ChatterMessage).filter_by(model_name='invoice').count() == 0


def test_credit_creation_preserves_original_and_blocks_duplicate(accounting_client):
    client, sessions, headers = accounting_client
    response = client.post('/v2/accounting/invoices', headers=headers, json={
        'client_name': 'Client', 'due_date': '2026-12-01T00:00:00',
        'lines': [{'description': 'Article', 'quantity': 1, 'unit_price': 100, 'tax_rate': 20}],
    })
    assert response.status_code == 200, response.text
    original = response.json()
    invoice_id = original['id']
    assert original['balance_due'] == 120
    assert original['can_pay'] is True
    pay = client.post(f'/v2/accounting/invoices/{invoice_id}/pay', headers=headers,
                      json={'amount': 40, 'method': 'CB'})
    assert pay.status_code == 200, pay.text
    assert pay.json()['balance_due'] == 80
    note = client.post(f'/v2/accounting/invoices/{invoice_id}/credit_note', headers=headers)
    assert note.status_code == 200, note.text
    assert note.json()['total'] == -120
    assert note.json()['balance_due'] == 0
    assert note.json()['customer_credit'] == 0  # credit belongs to source, no double counting
    assert note.json()['can_pay'] is False
    credited = listed(client, headers, invoice_id)
    assert credited['balance_due'] == 0
    assert credited['customer_credit'] == credited['refund_due'] == 40
    assert credited['status'] == 'PARTIAL'
    for field in ('reference', 'total', 'subtotal', 'tax_amount', 'qr_code_hash', 'previous_seal', 'lines'):
        assert credited[field] == original[field]
    assert client.post(f'/v2/accounting/invoices/{invoice_id}/credit_note', headers=headers).status_code == 400
    for endpoint, payload in [('pay', {'amount': 1, 'method': 'CB'}), ('remind', None), ('credit_note', None)]:
        assert client.post(f"/v2/accounting/invoices/{note.json()['id']}/{endpoint}", headers=headers, json=payload).status_code == 400
    with sessions() as db:
        assert db.query(models.Payment).count() == 1
        assert db.query(models.Invoice).count() == 2


def test_unrelated_and_draft_notes_do_not_cancel_receivable(accounting_client):
    client, sessions, headers = accounting_client
    invoice_id = seed(sessions, 40, ())
    with sessions() as db:
        db.add_all([
            models.Invoice(reference='AV-UNLINKED', total=-120, status='AVOIR',
                           client_name='Client', due_date=datetime(2026, 12, 1)),
            models.Invoice(reference='DRAFT-LINKED', total=-120, status='DRAFT', source_invoice_id=invoice_id,
                           invoice_type='CREDIT_NOTE', client_name='Client', due_date=datetime(2026, 12, 1)),
            models.Invoice(reference='CANCELLED-LINKED', total=-120, status='CANCELLED', source_invoice_id=invoice_id,
                           invoice_type='CREDIT_NOTE', client_name='Client', due_date=datetime(2026, 12, 1)),
        ])
        db.commit()
    invoice = listed(client, headers, invoice_id)
    assert invoice['balance_due'] == 80
    assert invoice['is_credited'] is False
    assert invoice['can_pay'] is True
    assert client.post(f'/v2/accounting/invoices/{invoice_id}/remind', headers=headers).status_code == 200
    assert client.post(f'/v2/accounting/invoices/{invoice_id}/pay', headers=headers,
                       json={'amount': 81, 'method': 'CB'}).status_code == 400
    paid = client.post(f'/v2/accounting/invoices/{invoice_id}/pay', headers=headers,
                       json={'amount': 80, 'method': 'CB'})
    assert paid.status_code == 200
    assert paid.json()['balance_due'] == 0
    assert paid.json()['status'] == 'PAID'
    assert client.post(f'/v2/accounting/invoices/{invoice_id}/remind', headers=headers).status_code == 400


def test_decimal_balance_and_excess_credit_are_not_fake_refunds():
    invoice = SimpleNamespace(total=Decimal('0.30'), payments=[SimpleNamespace(amount=Decimal('0.10'))],
                              status='PARTIAL', invoice_type='FINAL')
    balance = invoice_balance(invoice, Decimal('-0.20'))
    assert balance['balance_due'] == 0
    assert balance['customer_credit'] == 0
    assert balance['refund_due'] == 0
    balance = invoice_balance(invoice, Decimal('-0.40'))
    assert balance['customer_credit'] == Decimal('0.20')
    assert balance['refund_due'] == Decimal('0.10')


def test_partial_credit_remaining_balance_can_be_paid_and_reminded(accounting_client):
    client, sessions, headers = accounting_client
    invoice_id = seed(sessions, 40, (-60,))
    invoice = listed(client, headers, invoice_id)
    assert invoice['balance_due'] == 20
    assert invoice['net_total'] == 60
    assert invoice['can_pay'] is True
    assert invoice['can_remind'] is True
    assert client.post(f'/v2/accounting/invoices/{invoice_id}/remind', headers=headers).status_code == 200
    assert client.post(f'/v2/accounting/invoices/{invoice_id}/pay', headers=headers,
                       json={'amount': 21, 'method': 'CB'}).status_code == 400
    response = client.post(f'/v2/accounting/invoices/{invoice_id}/pay', headers=headers,
                           json={'amount': 20, 'method': 'CB'})
    assert response.status_code == 200, response.text
    paid = response.json()
    assert paid['status'] == 'PAID'
    assert paid['total_paid'] == 60
    assert paid['balance_due'] == paid['customer_credit'] == paid['refund_due'] == 0
    assert paid['can_pay'] is False
    assert paid['can_remind'] is False
    assert client.post(f'/v2/accounting/invoices/{invoice_id}/pay', headers=headers,
                       json={'amount': 1, 'method': 'CB'}).status_code == 400
    assert client.post(f'/v2/accounting/invoices/{invoice_id}/remind', headers=headers).status_code == 400
    with sessions() as db:
        assert db.query(models.Payment).count() == 2
        assert db.get(models.Invoice, invoice_id).qr_code_hash == 'original-seal'

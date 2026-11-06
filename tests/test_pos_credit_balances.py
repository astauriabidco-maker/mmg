from datetime import datetime

import pytest

from backend import models
from backend.core import security


@pytest.mark.parametrize('credited,due', [(120, 0), (60, 20)])
def test_pos_uses_linked_credit_balance_and_cannot_collect_twice(isolated_client, credited, due):
    client, factory = isolated_client
    with factory() as db:
        db.add(models.User(username='credit-cashier', role='ADMIN', pin_hash='unused', is_active=True))
        session = models.POSSession(reference='CREDIT-SESSION', status='OPEN', starting_cash=0)
        sale = models.SaleOrder(reference='CREDIT-SALE', client_name='Recipe', status='DELIVERED', workflow_type='FREE_SALE')
        db.add_all([session, sale])
        db.flush()
        invoice = models.Invoice(reference='CREDIT-INVOICE', sale_order_id=sale.id, client_name='Recipe',
                                 status='PARTIAL', invoice_type='FINAL', total=120,
                                 subtotal=100, tax_amount=20, due_date=datetime(2026, 12, 1))
        db.add(invoice)
        db.flush()
        db.add(models.Payment(invoice_id=invoice.id, amount=40, method='CB'))
        db.add(models.Invoice(reference='CREDIT-NOTE', sale_order_id=sale.id, source_invoice_id=invoice.id,
                              client_name='Recipe', status='AVOIR', invoice_type='CREDIT_NOTE',
                              total=-credited, due_date=datetime(2026, 12, 1)))
        db.commit()
        iid, sid = invoice.id, sale.id
    headers = {'Authorization': 'Bearer ' + security.create_access_token({'sub': 'credit-cashier', 'role': 'ADMIN'})}
    listing = client.get('/v2/pos/invoices/pending', headers=headers)
    assert listing.status_code == 200
    pending = listing.json()
    if due:
        assert len(pending) == 1 and pending[0]['due_amount'] == due
    else:
        assert pending == []
    response = client.post(f'/v2/pos/invoices/{iid}/pay', headers=headers,
                           json={'amount': due + 1, 'method': 'CASH', 'author': 'Recipe'})
    assert response.status_code == 400, response.text
    with factory() as db:
        assert db.query(models.Payment).count() == 1
        assert db.query(models.POSCashMovement).count() == 0
    detail = client.get(f'/v2/sales/{sid}', headers=headers)
    assert detail.status_code == 200, detail.text
    summary = next(i for i in detail.json()['invoices'] if i['id'] == iid)
    assert summary['balance_due'] == due
    assert summary['customer_credit'] == (40 if not due else 0)
    assert summary['is_credited'] is True
    if due:
        response = client.post(f'/v2/pos/invoices/{iid}/pay', headers=headers,
                               json={'amount': due, 'method': 'CB', 'author': 'Recipe'})
        assert response.status_code == 200, response.text
        assert client.get('/v2/pos/invoices/pending', headers=headers).json() == []
        with factory() as db:
            assert db.get(models.Invoice, iid).status == 'PAID'
            assert sum(float(p.amount) for p in db.query(models.Payment).all()) == 60
        assert client.post(f'/v2/pos/invoices/{iid}/pay', headers=headers,
                           json={'amount': 1, 'method': 'CB', 'author': 'Recipe'}).status_code == 400

import test from 'node:test';
import assert from 'node:assert/strict';
import { invoiceAccounting, accountingTotals } from '../src/utils/accounting.js';

const credited = {
    id: 8, total: 120, status: 'PARTIAL', payments: [{ amount: 40 }],
    total_paid: 40, balance_due: 0, customer_credit: 40, refund_due: 40,
    accounting_status: 'CREDITED', is_credited: true,
    can_pay: false, can_remind: false, can_credit: false,
};
const note = {
    total: -120, status: 'AVOIR', source_invoice_id: 8, accounting_status: 'AVOIR',
    balance_due: 0, customer_credit: 0, refund_due: 0,
    can_pay: false, can_remind: false, can_credit: false,
};

test('preprod 120 / payment 40 / credit note -120: zero due, refund pending 40', () => {
    assert.deepEqual(invoiceAccounting(credited), {
        status: 'CREDITED', due: 0, credit: 40, refund: 40,
        canPay: false, canRemind: false, canCredit: false,
    });
    assert.deepEqual(accountingTotals([credited, note]), { revenue: 0, paid: 40, due: 0, credit: 40, refund: 40 });
});

test('receivables and credits remain separate across customers', () => {
    const ordinary = { total: 120, status: 'PARTIAL', accounting_status: 'PARTIAL', balance_due: 80,
        can_pay: true, can_remind: true, can_credit: true };
    assert.deepEqual(accountingTotals([credited, note, ordinary]), { revenue: 120, paid: 40, due: 80, credit: 40, refund: 40 });
    assert.equal(invoiceAccounting(ordinary).canPay, true);
    const partial = { ...ordinary, accounting_status: 'PARTIALLY_CREDITED', balance_due: 20, can_pay: true, can_remind: true };
    assert.equal(invoiceAccounting(partial).due, 20);
    assert.equal(invoiceAccounting(partial).canRemind, true);
    assert.equal(invoiceAccounting(partial).canPay, true);
});

test('credit notes and unknown balances never offer collection actions', () => {
    assert.equal(invoiceAccounting({ ...note, can_pay: true, can_remind: true }).canPay, false);
    assert.equal(invoiceAccounting({ status: 'UNPAID', total: 120 }).canPay, false);
    assert.deepEqual(accountingTotals([{ ...credited, status: 'DRAFT' }]), { revenue: 0, paid: 0, due: 0, credit: 0, refund: 0 });
    assert.deepEqual(accountingTotals([{ ...note, status: 'CANCELLED' }]), { revenue: 0, paid: 0, due: 0, credit: 0, refund: 0 });
});

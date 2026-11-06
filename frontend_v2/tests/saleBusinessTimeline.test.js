import test from 'node:test';
import assert from 'node:assert/strict';
import { buildSaleBusinessTimeline, isSaleDelivered, canReturnSale } from '../src/utils/saleBusinessTimeline.js';

test('paid final invoice does not settle an unpaid or partially paid deposit', () => {
    for (const status of ['UNPAID', 'PARTIAL']) {
        const sale = { status: 'DELIVERED', workflow_type: 'FABRICATION_FROM_MEASURE', invoices: [
            { invoice_type: 'DEPOSIT', status, total: 390 },
            { invoice_type: 'FINAL', status: 'PAID', total: 390 },
        ] };
        const payment = buildSaleBusinessTimeline(sale).steps.find(step => step.key === 'payment');
        assert.equal(payment.detail, 'À encaisser');
        sale.invoices[0].status = 'PAID';
        assert.equal(buildSaleBusinessTimeline(sale).steps.find(step => step.key === 'payment').detail, 'Soldé');
    }
});

test('all production orders need a delivered BL, not just a signature timestamp', () => {
    const sale = { status: 'IN_PRODUCTION', production_orders: [{ id: 1 }, { id: 2 }], delivery_notes: [
        { order_id: 1, status: 'DELIVERED' },
        { order_id: 2, status: 'RETURNED', signed_at: '2026-11-06' },
    ] };
    assert.equal(isSaleDelivered(sale), false);
    sale.delivery_notes[1].status = 'DELIVERED';
    assert.equal(isSaleDelivered(sale), true);
});

test('return is only offered for a delivered free sale', () => {
    assert.equal(canReturnSale({ workflow_type: 'FREE_SALE', status: 'DELIVERED' }), true);
    assert.equal(canReturnSale({ workflow_type: 'FABRICATION_FROM_MEASURE', status: 'DELIVERED' }), false);
    assert.equal(canReturnSale({ workflow_type: 'FREE_SALE', status: 'CANCELLED' }), false);
});

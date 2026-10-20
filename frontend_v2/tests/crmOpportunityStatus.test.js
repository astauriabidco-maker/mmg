import assert from 'node:assert/strict';
import test from 'node:test';
import { isConvertedOpportunity, isOpenOpportunity } from '../src/utils/crmOpportunityStatus.js';

for (const stage of ['proposition_a_preparer', 'proposition_a_valider', 'proposition_envoyee', 'negociation']) {
    test(`${stage}: a linked quote remains open, not converted`, () => {
        const opportunity = { stage, sale_order_id: 11 };
        assert.equal(isConvertedOpportunity(opportunity), false);
        assert.equal(isOpenOpportunity(opportunity), true);
    });
}

test('legacy conversion flags and dates do not prove a signature', () => {
    const opportunity = {
        stage: 'proposition_a_valider', sale_id: 11, order_id: 11,
        converted: true, is_converted: true, converted_at: '2026-10-20', won_at: '2026-10-20',
    };
    assert.equal(isConvertedOpportunity(opportunity), false);
    assert.equal(isOpenOpportunity(opportunity), true);
});

for (const stage of ['gagne', 'WON']) {
    test(`${stage}: the signature-synchronized stage is converted and closed`, () => {
        assert.equal(isConvertedOpportunity({ stage, sale_order_id: 12 }), true);
        assert.equal(isOpenOpportunity({ stage, sale_order_id: 12 }), false);
    });
}

for (const stage of ['perdu', 'LOST', 'CANCELLED', 'CLOSED']) {
    test(`${stage}: closed without a conversion`, () => {
        assert.equal(isConvertedOpportunity({ stage, sale_order_id: 11 }), false);
        assert.equal(isOpenOpportunity({ stage, sale_order_id: 11 }), false);
    });
}

test('a new need is open without a quote', () => {
    assert.equal(isConvertedOpportunity({ stage: 'nouveau' }), false);
    assert.equal(isOpenOpportunity({ stage: 'nouveau' }), true);
});

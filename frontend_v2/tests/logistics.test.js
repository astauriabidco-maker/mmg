import test from 'node:test';
import assert from 'node:assert/strict';
import { routePayload, logisticsError } from '../src/utils/logistics.js';

test('route sends an explicit midnight datetime, not a bare date', () => {
    const payload = routePayload({ driver_name: ' Recipe ', planned_date: '2026-10-21', note_ids: [2] });
    assert.equal(payload.planned_date, '2026-10-21T00:00:00');
    assert.equal(payload.driver_name, 'Recipe');
});
test('missing required values and API validation remain readable', () => {
    assert.throws(() => routePayload({ driver_name: 'A', planned_date: '', note_ids: [] }));
    assert.equal(logisticsError({ response: { data: { detail: [{ msg: 'Date invalide' }] } } }), 'Date invalide');
});

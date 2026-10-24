test('switching a free preference to a priced choice does not discard entered prices', () => {
  const payload = catalog.optionChoicePayload({ code: 'synthetic', name: 'Synthetic', choice_type: 'dedicated_charge', charge_mode: 'free', prices: [{ price_type: 'store', amount_cents: 4990 }] });
  assert.equal(payload.charge_mode, 'custom_price');
  assert.deepEqual(payload.prices, [{ price_type: 'store', amount_cents: 4990 }]);
});
import assert from 'node:assert/strict';
import test from 'node:test';
import * as catalog from '../src/catalogOptions.ts';

test('linked project labels show named yuan amounts rather than serialized data', () => {
  assert.equal((catalog as any).linkedProjectLabel?.({ name: '头疗', prices: { group: 5900, member: 4900, store: 7900 } }), '头疗 · 门店 ¥79.00 / 会员 ¥49.00 / 团购 ¥59.00');
});

test('missing price stays unconfigured while zero is a real displayed price', () => {
  assert.equal((catalog as any).linkedProjectLabel?.({ name: '测试项目', prices: { store: 0 } }), '测试项目 · 门店 ¥0.00 / 会员 未配置 / 团购 未配置');
});

test('editor currency conversion retains cents and never converts an empty value to zero', () => {
  assert.equal((catalog as any).yuanToCents?.(49.9), 4990);
  assert.equal((catalog as any).yuanToCents?.(0), 0);
  assert.equal((catalog as any).yuanToCents?.(null), null);
  assert.equal((catalog as any).yuanToCents?.(undefined), undefined);
});

test('editor currency conversion rejects nonfinite and negative input', () => {
  assert.throws(() => (catalog as any).yuanToCents?.(Number.NaN), /金额/);
  assert.throws(() => (catalog as any).yuanToCents?.(-1), /金额/);
});

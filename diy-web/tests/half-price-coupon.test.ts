import assert from 'node:assert/strict';
import test from 'node:test';
import { availableHalfPriceCoupon, halfPriceForProject } from '../src/halfPriceCoupon.ts';
import type { MyCoupon } from '../src/api.ts';
import type { Project } from '../src/domain.ts';

const now = Date.parse('2026-11-12T12:00:00Z');
const coupon: MyCoupon = { id: 1, name: 'Main project voucher', store_id: 1, usage_scope: 'foot_spa_main', coupon_type: 'percent', percent_off: 50, amount_cents: 0, min_spend_cents: 0, status: 'unused', claimed_at: null, expire_at: '2026-12-12T12:00:00Z' };

test('only an unused unexpired matching-store main-project voucher enables price display', () => {
  assert.equal(availableHalfPriceCoupon([coupon], 1, now)?.id, 1);
  assert.equal(availableHalfPriceCoupon([], 1, now), null);
  for (const invalid of [{ status: 'used' }, { status: 'locked' }, { status: 'expired' }, { store_id: 2 }, { usage_scope: null }, { percent_off: 20 }, { min_spend_cents: 100 }, { expire_at: null }, { expire_at: 'invalid' }, { expire_at: '2026-11-12T12:00:00Z' }]) {
    assert.equal(availableHalfPriceCoupon([{ ...coupon, ...invalid }], 1, now), null);
  }
});

test('menu uses server price, never halves membership or estimates excluded categories', () => {
  const project = { prices: [{ price_type: 'store', amount_cents: 8900 }, { price_type: 'member', amount_cents: 5900 }], half_price_coupon_price_cents: 4450 } as Project;
  assert.equal(halfPriceForProject(project, true), 4450);
  assert.equal(halfPriceForProject(project, false), null);
  for (const price of [undefined, null, 0, -1, 44.5, NaN]) assert.equal(halfPriceForProject({ ...project, half_price_coupon_price_cents: price }, true), null);
});

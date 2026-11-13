import test from 'node:test';
import assert from 'node:assert/strict';
import { budgetLabel, couponDiscountLabel, formatMoney, percentOffLabel } from '../src/utils/couponFormat.ts';

test('percent_off is the percentage removed, not the Chinese discount rate', () => {
  assert.equal(couponDiscountLabel({ coupon_type: 'percent', percent_off: 20 }), '8折');
  assert.equal(couponDiscountLabel({ coupon_type: 'percent', percent_off: 50 }), '5折');
  assert.equal(couponDiscountLabel({ coupon_type: 'percent', percent_off: 80 }), '2折');
  assert.equal(percentOffLabel(8.5), '比例缺失');
});

test('money keeps half-yuan precision and budget zero is not unlimited', () => {
  assert.equal(formatMoney(5950), '¥59.50');
  assert.equal(formatMoney(500), '¥5');
  assert.equal(couponDiscountLabel({ coupon_type: 'fixed', amount_cents: 5950 }), '¥59.50');
  assert.equal(budgetLabel(null), '不限预算');
  assert.equal(budgetLabel(0), '零预算');
  assert.equal(budgetLabel(10000), '¥100');
});

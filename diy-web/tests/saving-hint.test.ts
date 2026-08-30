import assert from 'node:assert/strict';
import test from 'node:test';

import { selectSavingHint, type SavingHint } from '../src/savingHint.ts';

test('有明确会员节省金额时优先展示会员登录引导', () => {
  const member: SavingHint = { kind: 'member', estimated_saving_cents: 1000, login_required: true };
  const coupon: SavingHint = { kind: 'coupon', login_required: true };

  assert.deepEqual(selectSavingHint(member, coupon), member);
});

test('没有会员差价时可展示不承诺金额的领券引导', () => {
  const coupon: SavingHint = { kind: 'coupon', login_required: true };

  assert.deepEqual(selectSavingHint(null, coupon), coupon);
  assert.equal(selectSavingHint(null, null), null);
});

test('会员差价为零时不展示会员引导，也不回退到空券位', () => {
  const zeroSaving: SavingHint = { kind: 'member', estimated_saving_cents: 0, login_required: true };

  assert.equal(selectSavingHint(zeroSaving, null), null);
});

test('会员差价缺失或未登录标记时不承诺金额', () => {
  const noAmount: SavingHint = { kind: 'member', login_required: true };

  assert.equal(selectSavingHint(noAmount, null), null);
});

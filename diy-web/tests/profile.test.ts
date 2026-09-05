import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';

import {
  ANNUAL_MEMBERSHIP_BENEFITS,
  canSelfCancelOrder,
  couponStatusLabel,
  formatDateTime,
  maskedPhone,
  membershipSavingCents,
  membershipState,
  recordFilter,
  orderStatusLabel,
  selectionStatusLabel,
  selectionDisplayAmount,
} from '../src/profile.ts';

test('手机号中间四位脱敏', () => {
  assert.equal(maskedPhone('17601019659'), '176****9659');
  assert.equal(maskedPhone('123'), '123');
  assert.equal(maskedPhone(''), '');
});

test('会员累计节省只统计已完成服务的历史门店价与会员价差额', () => {
  assert.equal(membershipSavingCents([
    { service_completed_at: '2026-09-01T10:00:00Z', store_total_cents: 33600, member_total_cents: 23600 },
    { service_completed_at: null, store_total_cents: 9900, member_total_cents: 6900 },
    { service_completed_at: '2026-09-02T10:00:00Z', store_total_cents: 3990, member_total_cents: 3990 },
  ]), 10000);
});

test('会员有效期映射为有效、临期和过期状态', () => {
  assert.deepEqual(membershipState('2026-10-20T00:00:00Z', new Date('2026-09-05T00:00:00Z')), { kind: 'active', daysLeft: 45 });
  assert.deepEqual(membershipState('2026-09-20T00:00:00Z', new Date('2026-09-05T00:00:00Z')), { kind: 'expiring', daysLeft: 15 });
  assert.deepEqual(membershipState('2026-09-04T00:00:00Z', new Date('2026-09-05T00:00:00Z')), { kind: 'expired', daysLeft: 0 });
});

test('会员卡提供动态会员码且明确30秒刷新和可信设备边界', () => {
  const source = fs.readFileSync(new URL('../src/components/ProfilePage.tsx', import.meta.url), 'utf8');
  assert.match(source, /出示动态会员码/);
  assert.match(source, /30 秒/);
  assert.match(source, /issueMemberCode/);
  assert.match(source, /enrollTrustedDevice/);
});

test('到店记录可按待评价和服务状态筛选', () => {
  const records = [
    { id: 'a', can_evaluate: true, evaluated: false, occupancy_status: 'post_service_present' },
    { id: 'b', can_evaluate: true, evaluated: true, occupancy_status: 'post_service_present' },
    { id: 'c', can_evaluate: false, evaluated: false, occupancy_status: 'in_service' },
  ];
  assert.deepEqual(recordFilter(records, 'pending-feedback').map((item) => item.id), ['a']);
  assert.deepEqual(recordFilter(records, 'in-service').map((item) => item.id), ['c']);
  assert.deepEqual(recordFilter(records, 'completed').map((item) => item.id), ['a', 'b']);
});

test('订单状态映射为顾客可读文案', () => {
  assert.equal(orderStatusLabel('pending_payment'), '待前台确认');
  assert.equal(orderStatusLabel('in_service'), '服务中');
  assert.equal(orderStatusLabel('pending_checkout'), '待结算');
  assert.equal(orderStatusLabel('pending_feedback'), '待评价');
  assert.equal(orderStatusLabel('completed'), '已完成');
  assert.equal(orderStatusLabel('refund_pending'), '退款处理中');
  assert.equal(orderStatusLabel('unknown-status'), 'unknown-status');
});

test('仅待支付订单可自助取消', () => {
  assert.equal(canSelfCancelOrder('pending_payment'), true);
  assert.equal(canSelfCancelOrder('paid'), false);
  assert.equal(canSelfCancelOrder('completed'), false);
  assert.equal(canSelfCancelOrder('cancelled'), false);
});

test('选单状态映射为顾客可读文案', () => {
  assert.equal(selectionStatusLabel('submitted'), '待前台确认');
  assert.equal(selectionStatusLabel('confirmed'), '已由门店确认');
  assert.equal(selectionStatusLabel('draft'), '选购中');
});

test('到店记录优先显示服务端当前预计或冻结金额，不把会员参考价当成非会员应付金额', () => {
  assert.equal(selectionDisplayAmount({
    pricing_snapshot: { applied_price_type: 'store', payable_total_cents: 3990 },
    store_total_cents: 3990,
    member_total_cents: 2990,
  }), 3990);
  assert.equal(selectionDisplayAmount({
    pricing_snapshot: { applied_price_type: 'member' },
    store_total_cents: 3990,
    member_total_cents: 2990,
  }), 2990);
  assert.equal(selectionDisplayAmount({ store_total_cents: 3990, member_total_cents: 2990 }), 3990);
});

test('年度权益卡准确说明周二低价规则与一次赠送规则', () => {
  assert.equal(ANNUAL_MEMBERSHIP_BENEFITS.tuesday, '每周二，会员价与门店价 6.8 折取较低价');
  assert.equal(ANNUAL_MEMBERSHIP_BENEFITS.gift, '办理会员年度权益卡时，可获赠 1 项门店价 99 元以下项目；仅赠送一次，不与其他优惠叠加');
});

test('优惠券状态映射', () => {
  assert.equal(couponStatusLabel('unused'), '未使用');
  assert.equal(couponStatusLabel('used'), '已使用');
  assert.equal(couponStatusLabel('expired'), '已过期');
});

test('ISO 时间格式化为本地可读时间', () => {
  assert.match(formatDateTime('2026-08-14T09:30:00'), /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
  assert.equal(formatDateTime(null), '');
  assert.equal(formatDateTime('not-a-date'), '');
});

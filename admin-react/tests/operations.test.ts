import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildAbnormalSelectionSettlementPayload,
  buildRefundNotePayload,
  buildSelectionSettlementPayload,
  canFinishRoomCleaning,
  getOperationConfirmation,
  getNextOperation,
  getResourceStatus,
  makeIdempotencyKey,
} from '../src/operations.ts';

test('服务完成后按冻结价格生成结算请求', () => {
  assert.deepEqual(buildSelectionSettlementPayload(2990, 'wechat_scan', '服务完成后收款'), {
    payment_method: 'wechat_scan',
    received_amount_cents: 2990,
    payment_reference: '',
    reason: '服务完成后收款',
  });
});

test('异常服务结算明确携带减免、原因和责任归属', () => {
  assert.deepEqual(buildAbnormalSelectionSettlementPayload({
    originalPayableCents: 2990,
    adjustmentCents: 1000,
    paymentMethod: 'cash',
    reasonCode: 'service_aborted',
    responsibility: 'store',
    reason: '服务中止，减免部分费用',
  }), {
    payment_method: 'cash',
    received_amount_cents: 1990,
    payment_reference: '',
    service_adjustment_cents: 1000,
    adjustment_reason_code: 'service_aborted',
    responsibility: 'store',
    reason: '服务中止，减免部分费用',
  });
});

test('退款登记负载保留金额、渠道凭证和责任信息', () => {
  assert.deepEqual(buildRefundNotePayload({
    amountCents: 500,
    reasonCode: 'customer_complaint',
    responsibility: 'store',
    refundReference: 'OFFLINE-1',
    reason: '线下退款',
  }), {
    amount_cents: 500,
    reason_code: 'customer_complaint',
    responsibility: 'store',
    refund_reference: 'OFFLINE-1',
    reason: '线下退款',
  });
});

test('uses the operation label directly in confirmation copy', () => {
  assert.equal(getOperationConfirmation('确认入座'), '确认入座？');
  assert.equal(getOperationConfirmation('上钟'), '上钟？');
});

test('只映射 DIY 可执行的确认服务和服务结束动作', () => {
  assert.equal(getNextOperation('waiting_assignment', 'draft'), null);
  assert.deepEqual(getNextOperation('assigned', 'assigned'), {
    action: 'ready',
    label: '确认服务',
  });
  assert.equal(getNextOperation('assigned', 'ready'), null);
  assert.deepEqual(getNextOperation('in_service', 'in_service'), {
    action: 'finish',
    label: '服务结束',
  });
  assert.equal(getNextOperation('pending_checkout', 'pending_checkout'), null);
});

test('does not offer an operation for completed or inconsistent states', () => {
  assert.equal(getNextOperation('completed', 'completed'), null);
  assert.equal(getNextOperation('waiting_assignment', 'in_service'), null);
});

test('creates distinct bounded idempotency keys', () => {
  const first = makeIdempotencyKey('check-in', 42);
  const second = makeIdempotencyKey('check-in', 42);

  assert.notEqual(first, second);
  assert.ok(first.startsWith('check-in-42-'));
  assert.ok(first.length <= 64);
});

test('only offers room cleaning when the server marks it as allowed', () => {
  assert.equal(canFinishRoomCleaning({
    id: 1,
    name: '1号沙发',
    status: 'cleaning',
    can_finish_cleaning: true,
  }), true);
  assert.equal(canFinishRoomCleaning({
    id: 2,
    name: '2号沙发',
    status: 'cleaning',
    can_finish_cleaning: false,
  }), false);
});

test('maps operational resource states to concise Chinese labels', () => {
  assert.deepEqual(getResourceStatus('busy'), { color: 'purple', text: '忙碌' });
  assert.deepEqual(getResourceStatus('inspection'), { color: 'gold', text: '检查中' });
  assert.deepEqual(getResourceStatus('maintenance'), { color: 'red', text: '维护中' });
  assert.deepEqual(getResourceStatus('resting'), { color: 'default', text: '休息中' });
  assert.deepEqual(getResourceStatus('unknown'), { color: 'default', text: 'unknown' });
});

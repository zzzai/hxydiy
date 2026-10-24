import assert from 'node:assert/strict';
import test from 'node:test';
import { attentionDestination, displayCount, exceptionLabel, exceptionStatus, readExceptions, selectionSource, serviceStatus } from '../src/dailyOperations.ts';

test('unknown data does not masquerade as a successful zero', () => {
  for (const value of [undefined, null, '0', NaN, -1, {}]) assert.equal(displayCount(value), '—');
  assert.equal(displayCount(0), 0); assert.equal(displayCount(12), 12);
});
test('attention entries navigate to the actual operational destination', () => {
  assert.equal(attentionDestination('exception_queue'), '/exceptions');
  assert.equal(attentionDestination('exception_overdue'), '/exceptions');
  assert.equal(attentionDestination('low_review'), '/feedback');
  assert.equal(attentionDestination('unassigned_service'), '/service-positions');
  assert.equal(attentionDestination('stale_order'), '/selection-sessions');
  assert.equal(attentionDestination('record_pending'), null);
});
test('acknowledged issues remain distinct from resolved records', () => {
  const rows = readExceptions({ items: [{ id: 1, status: 'open' }, { id: 2, status: 'acknowledged' }, { id: 3, status: 'resolved' }] });
  assert.equal(rows.length, 3);
  assert.match(exceptionStatus(rows[1].status), /待处理/);
  assert.match(exceptionStatus(rows[2].status), /处理结果/);
});
test('malformed responses are errors rather than empty queues', () => {
  for (const value of [null, {}, {items: null}, {items: [{}]}, {items: [{id: 1, status: 'unknown'}]}]) assert.throws(() => readExceptions(value));
  assert.deepEqual(readExceptions({items: []}), []);
});
test('technical enums do not escape into business labels', () => {
  assert.equal(exceptionLabel('new_internal_enum'), '服务信息需要核对');
  assert.equal(serviceStatus('new_internal_enum'), '进度待核实');
  assert.equal(selectionSource('personal_qr'), '顾客扫码');
  assert.equal(selectionSource('in_store'), '到店选购');
  assert.equal(selectionSource('new_internal_enum'), '门店入口');
});

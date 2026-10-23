import assert from 'node:assert/strict';
import test from 'node:test';
import { readUnresolvedTasks } from '../src/technician/managerTasks.ts';

test('acknowledged issues remain actionable but resolved and duplicate issues do not inflate counts', () => {
  const result = readUnresolvedTasks({ items: [
    { id: 1, status: 'open', exception_type: 'missing_order', title: 'confirmed technical text', detail: { secret: 'private' } },
    { id: 2, status: 'acknowledged', exception_type: 'status_mismatch', assigned_to: 'Test manager' },
    { id: 2, status: 'acknowledged', exception_type: 'status_mismatch' },
    { id: 3, status: 'resolved', exception_type: 'missing_order' },
  ] });
  assert.deepEqual(result.map(item => [item.id, item.status]), [[1, 'open'], [2, 'acknowledged']]);
  assert.equal(result[1].label, '服务进度需要核对');
  assert.equal(result[1].assigned_to, 'Test manager');
  assert.equal(JSON.stringify(result).includes('technical'), false);
  assert.equal(JSON.stringify(result).includes('private'), false);
});

test('unsupported issue types have a customer-facing fallback without echoing internal codes', () => {
  const result = readUnresolvedTasks({ items: [{ id: 4, status: 'open', exception_type: 'internal_type' }] });
  assert.equal(result[0].label, '服务信息需要核对');
  assert.equal(JSON.stringify(result).includes('internal_type'), false);
});

test('malformed responses do not masquerade as an empty successful queue', () => {
  assert.throws(() => readUnresolvedTasks({}));
  assert.throws(() => readUnresolvedTasks({ items: null }));
  assert.deepEqual(readUnresolvedTasks({ items: [] }), []);
});

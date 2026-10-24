import assert from 'node:assert/strict';
import test from 'node:test';
import { auditDetailRows, segmentConditions, segmentSummary, automationActionText, disabledTagRule } from '../src/businessDisplay.ts';
test('audit projection ignores nested data, secret-shaped fields and unrecognized fields', () => {
  const value = { project_id: 4, version: 2, token: 'private', reason: { raw: 'hidden' }, name: 'private', arbitrary: 3 };
  assert.deepEqual(auditDetailRows(value), [{ label: '项目编号', value: '4' }, { label: '版本', value: '2' }]);
  assert.deepEqual(value.reason, { raw: 'hidden' });
});
test('segment form emits only supported predicates with any-tag membership semantics', () => {
  assert.deepEqual(segmentConditions({ tags: ['A','A','B'], memberOnly: true }), { tags: ['A','B'], is_member: true });
  assert.deepEqual(segmentConditions({ tags: [], memberOnly: false }), {});
  assert.match(segmentSummary({ tags: ['A','B'], is_member: true }).join(' '), /任一标签.*会员标记/);
  assert.match(segmentSummary({ unknown: 'hidden' }).join(' '), /待核验|需核验/);
});
test('automation draft always remains disabled and contains only selected existing tag action', () => {
  const result = disabledTagRule({ name: ' Test ', trigger_event: 'order_completed', action: 'add_tag', tag_id: 3 });
  assert.equal(result.is_enabled, false); assert.equal(result.name, 'Test');
  assert.deepEqual(result.actions, [{ type: 'add_tag', tag_id: 3 }]);
});
test('automation presentation never falls back to raw objects or unknown enum values', () => {
  assert.equal(automationActionText({ type: 'internal_debug', raw: 'private' }), '旧版动作待核验');
  assert.equal(automationActionText({ type: 'add_tag', tag_id: 2 }), '添加顾客标签 · 标签编号 2');
});

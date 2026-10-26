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

test('notification audit explains API acceptance without exposing raw payloads', () => {
  const rows = auditDetailRows({status:'accepted',recipient_count:1,accepted_count:1,invalid_count:0,attempt_id:'opaque',token:'hidden',note:'private'}, 'wecom_feedback_notify');
  assert.deepEqual(rows, [{label:'通知结果',value:'企微已受理（不代表已读）'},{label:'目标人数',value:'1'},{label:'企微受理人数',value:'1'},{label:'未受理人数',value:'0'}]);
  assert.deepEqual(auditDetailRows({status:'unexpected',raw:{token:'hidden'}}, 'wecom_feedback_notify'), [{label:'通知结果',value:'结果待核验'}]);
});

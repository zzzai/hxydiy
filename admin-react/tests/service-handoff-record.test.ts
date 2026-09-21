import test from 'node:test';
import assert from 'node:assert/strict';
import { buildHandoffPayload, handoffPreview, hasHandoffContent, makeHandoff } from '../src/technician/serviceHandoffRecord.ts';

test('builds stable v7 handoff payload without inventing confirmation', () => {
  const record = {
    ...makeHandoff(),
    communication: 'quiet' as const,
    body_focus: [{ region: 'neck_shoulder' as const, next_action: 'lighter' as const }],
  };
  const payload = buildHandoffPayload(7, 'session-a', record, false);
  assert.equal(payload.schema_version, 7);
  assert.equal(payload.taxonomy_version, 'service_handoff_v1');
  assert.equal(payload.customer_confirmed, false);
  assert.deepEqual(handoffPreview(record), ['顾客想安静休息', '肩颈下次轻一些']);
});

test('body focus is limited to three unique paired entries', () => {
  const duplicate = {
    ...makeHandoff(),
    body_focus: [
      { region: 'knee' as const, next_action: 'focus' as const },
      { region: 'knee' as const, next_action: 'confirm' as const },
    ],
  };
  assert.throws(() => buildHandoffPayload(7, 'session', duplicate, false), /同一部位/);
  const unpaired = { ...makeHandoff(), body_focus: [{ region: 'knee' as const, next_action: undefined }] };
  assert.throws(() => buildHandoffPayload(7, 'session', unpaired, false), /处理方式/);
});

test('no-new is exclusive and optional basic info counts as content', () => {
  assert.equal(hasHandoffContent({ ...makeHandoff(), basic_info: { gender: 'female' } }), true);
  assert.throws(() => buildHandoffPayload(7, 'session', { ...makeHandoff(), communication: 'chat', recording_outcome: 'no_additional_notes' }, false));
});

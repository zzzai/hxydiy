import test from 'node:test';
import assert from 'node:assert/strict';
import { makeRecord, buildRecordPayload, hasRecordContent } from '../src/technician/projectServiceRecord.ts';

test('only flagship item selects flagship template; unrelated items remain generic', () => {
  assert.equal(makeRecord([{name: '招牌草本泡'}]).template, 'herbal_signature_v1');
  assert.equal(makeRecord([{name: '采耳'}]).template, 'general_v1');
  assert.equal(makeRecord([{code:'hxy-xiaoqi-90',name:'已更新的展示名称'}]).template,'herbal_signature_v1');
  assert.equal(makeRecord([{code:'hxy-caier-30',name:'招牌草本泡'}]).template,'general_v1');
});
test('request alone does not imply action, feedback or confirmation', () => {
  const value = {...makeRecord([{name:'招牌草本泡'}]), massage:[{region:'shoulder', side:'left', request:'lighter'}]};
  const result = buildRecordPayload(7, 'session-a', value, false);
  assert.deepEqual(result.profile.massage, [{region:'shoulder', side:'left', request:'lighter'}]);
  assert.equal(result.customer_confirmed, false);
  assert.equal(result.schema_version, 6);
});
test('communication alone is content; empty is not; no-new cannot erase contents', () => {
  assert.equal(hasRecordContent(makeRecord([])), false);
  assert.equal(hasRecordContent({...makeRecord([]),communication:'quiet'}), true);
  assert.throws(() => buildRecordPayload(7,'session', {...makeRecord([]), communication:'quiet', recording_outcome:'no_additional_notes'},false));
});

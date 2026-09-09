import assert from 'node:assert/strict';
import test from 'node:test';
import { buildServiceReferenceV5Payload, hasServiceReferenceInput } from '../src/technician/serviceReference.ts';

test('技师补充文字保持观察来源，不写入顾客原话', () => {
  const result = buildServiceReferenceV5Payload(12, 'service-1', { serviceNote: '  安静休息  ', forcePreference: 'gentle' });
  assert.deepEqual(result.profile.technician_observed, { service_note: '安静休息' });
  assert.deepEqual(result.profile.customer_reported, { force_preference: 'gentle' });
  assert.equal(result.customer_confirmed, false);
  assert.equal(result.source, 'service_observation');
});

test('无补充不自动生成满意或顾客确认，不能与实际记录混写', () => {
  const result = buildServiceReferenceV5Payload(12, 'service-1', { recordingOutcome: 'no_additional_notes' });
  assert.deepEqual(result.profile.technician_observed, { recording_outcome: 'no_additional_notes' });
  assert.deepEqual(result.profile.customer_reported, {});
  assert.equal(result.customer_confirmed, false);
  assert.throws(() => buildServiceReferenceV5Payload(12, 'service-1', { recordingOutcome: 'no_additional_notes', serviceNote: '已有记录' }));
  assert.throws(() => buildServiceReferenceV5Payload(12, 'service-1', { recordingOutcome: 'no_additional_notes', customerConfirmed: true }));
});

test('顾客明确要求安静时保存为可复用的服务沟通偏好', () => {
  assert.equal(hasServiceReferenceInput({ communicationPreference: 'quiet' }), true);
  const result = buildServiceReferenceV5Payload(12, 'service-1', { communicationPreference: 'quiet' });
  assert.deepEqual(result.profile.customer_reported, { communication_preference: 'quiet' });
  assert.deepEqual(result.profile.technician_observed, {});
});

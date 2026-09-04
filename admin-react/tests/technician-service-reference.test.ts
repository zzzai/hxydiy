import assert from 'node:assert/strict';
import test from 'node:test';
import {
  SERVICE_REFERENCE_OPTIONS,
  buildServiceReferencePayload,
  hasServiceReferenceInput,
} from '../src/technician/serviceReference.ts';

test('服务参考使用稳定编码而非中文展示值', () => {
  assert.deepEqual(SERVICE_REFERENCE_OPTIONS.focusAreas[0], { label: '肩颈', value: 'neck_shoulder' });
  assert.equal(SERVICE_REFERENCE_OPTIONS.force[1].value, 'medium');
  assert.equal(SERVICE_REFERENCE_OPTIONS.nextVisit[0].value, 'repeat_current');
});

test('服务参考请求保留选择顺序、空数组和确认来源', () => {
  const payload = buildServiceReferencePayload(12, 'session-1', {
    focusAreas: ['legs', 'neck_shoulder'],
    avoidAreas: [],
    forcePreference: 'medium',
    temperaturePreference: 'lower',
    serviceFeedback: 'better_after_adjustment',
    nextVisitPlan: 'repeat_current',
    customerConfirmed: true,
    quote: ' 肩颈重点，温度低一点 ',
  });

  assert.equal(payload.schema_version, 2);
  assert.equal(payload.taxonomy_version, 'service_reference_v1');
  assert.equal(payload.customer_confirmed, true);
  assert.equal(payload.source, 'both');
  assert.deepEqual(payload.profile.customer_reported.focus_areas, ['legs', 'neck_shoulder']);
  assert.deepEqual(payload.profile.customer_reported.avoid_areas, []);
  assert.equal(payload.profile.customer_reported.quote, '肩颈重点，温度低一点');
});

test('空服务参考不可提交，未确认记录使用服务观察来源', () => {
  assert.equal(hasServiceReferenceInput({}), false);
  assert.equal(hasServiceReferenceInput({ focusAreas: [] }), false);
  assert.equal(hasServiceReferenceInput({ temperaturePreference: 'higher' }), true);
  const payload = buildServiceReferencePayload(1, 'session-2', { temperaturePreference: 'higher' });
  assert.equal(payload.customer_confirmed, false);
  assert.equal(payload.source, 'service_observation');
});

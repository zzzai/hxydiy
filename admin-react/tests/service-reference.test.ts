import assert from 'node:assert/strict';
import test from 'node:test';
import { buildServiceReferenceV3Payload } from '../src/technician/serviceReference.ts';

test('服务参考 v3 载荷固定版本并保留可选字段的最小结构', () => {
  const payload = buildServiceReferenceV3Payload(12, 'session-v3', {
    customerConfirmed: true,
    personalContext: { ageBand: '25_34', build: 'balanced' },
    workLifestyle: { occupationContexts: ['desk_work'], sleepQuality: 'average' },
    serviceRelatedContext: { contexts: ['medication_mentioned'], quote: ' 顾客自述正在用药 ' },
    sessionResponse: { relaxation: 'gradual' },
  });

  assert.equal(payload.schema_version, 3);
  assert.equal(payload.taxonomy_version, 'service_reference_v2');
  assert.equal(payload.customer_confirmed, true);
  assert.deepEqual(payload.signals, []);
  assert.equal(payload.note, '');
  assert.deepEqual(payload.profile.customer_reported.personal_context, { age_band: '25_34', build: 'balanced' });
  assert.equal(payload.profile.customer_reported.service_related_context.quote, '顾客自述正在用药');
  assert.deepEqual(payload.profile.technician_observed.session_response, { relaxation: 'gradual' });
});

test('服务参考 v3 无可选值时构造合法最小载荷', () => {
  const payload = buildServiceReferenceV3Payload(12, 'session-v3-minimum', {});

  assert.equal(payload.customer_confirmed, false);
  assert.deepEqual(payload.profile.customer_reported, {});
  assert.deepEqual(payload.profile.technician_observed, {});
  assert.deepEqual(payload.profile.next_visit, {});
});

test('服务参考 v3 单一载荷同时保存高频六组和扩展偏好', () => {
  const payload = buildServiceReferenceV3Payload(12, 'session-v3-mixed', {
    focusAreas: ['neck_shoulder', 'legs'], avoidAreas: ['abdomen'],
    forcePreference: 'medium', temperaturePreference: 'lower', serviceFeedback: 'suitable', nextVisitPlan: 'repeat_current',
    personalContext: { ageBand: '65_plus', build: 'slim' },
    communicationConsumption: { decisionPriorities: ['quality'], budgetPreference: 'balanced' },
  });
  assert.deepEqual(payload.profile.customer_reported.focus_areas, ['neck_shoulder', 'legs']);
  assert.equal(payload.profile.technician_observed.service_feedback, 'suitable');
  assert.equal(payload.profile.next_visit.plan, 'repeat_current');
  assert.deepEqual(payload.profile.customer_reported.communication_consumption, { decision_priorities: ['quality'], budget_preference: 'balanced' });
});

test('服务参考 v3 兼容旧原话入口但拒绝两个不同原话静默覆盖', () => {
  const compatible = buildServiceReferenceV3Payload(12, 'session-v3-quote', { quote: ' 顾客说温度低一点 ' });
  assert.equal(compatible.profile.customer_reported.service_related_context.quote, '顾客说温度低一点');
  assert.throws(() => buildServiceReferenceV3Payload(12, 'session-v3-two-quotes', {
    quote: '第一段', serviceRelatedContext: { quote: '第二段' },
  }), /只能填写一处/);
});

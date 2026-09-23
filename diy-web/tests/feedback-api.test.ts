import assert from 'node:assert/strict';
import test from 'node:test';

import { createVisitFeedbackEntry, getServiceStatus, submitFeedback, submitVisitFeedback } from '../src/api.ts';

test('bed QR obtains a feedback token without creating a selection session', async () => {
  const calls: Array<{ url: string; options: RequestInit }> = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input, options = {}) => {
    calls.push({ url: String(input), options });
    return new Response(JSON.stringify({
      visit_feedback_token: 'vf1.signed.feedback',
      store_id: 7,
      position_code: 'bed-01',
      position_label: '1',
    }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  }) as typeof fetch;
  try {
    const entry = await createVisitFeedbackEntry({
      store_id: 7, position_code: 'bed-01', source: 'room_qr', entry_token: 'signed-bed-qr',
    });
    assert.equal(entry.visit_feedback_token, 'vf1.signed.feedback');
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, '/api/v1/visit-feedback/entry');
    assert.equal(calls[0].options.credentials, 'include');
    assert.deepEqual(JSON.parse(String(calls[0].options.body)), {
      store_id: 7, position_code: 'bed-01', source: 'room_qr', entry_token: 'signed-bed-qr',
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('评价 API 使用选单令牌并传递评价内容', async () => {
  const calls: Array<{ url: string; options: RequestInit }> = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input, options = {}) => {
    calls.push({ url: String(input), options });
    return new Response(JSON.stringify({
      selection_session_id: 'session-1',
      occupancy_status: 'post_service_present',
      service_ended_at: '2026-08-11T10:00:00Z',
      can_evaluate: true,
      evaluated: false,
      id: 4,
      rating: 5,
      tags: ['服务细致'],
      note: '很好',
      submitted: true,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  }) as typeof fetch;

  try {
    const status = await getServiceStatus('session-1', 'token-1');
    const feedback = await submitFeedback('session-1', 'token-1', {
      rating: 5,
      tags: ['服务细致'],
      note: '很好',
    });

    assert.equal(status.can_evaluate, true);
    assert.equal(feedback.submitted, true);
    assert.equal(calls[0].url, '/api/v1/selection-sessions/session-1/service-status');
    assert.equal(calls[1].url, '/api/v1/selection-sessions/session-1/feedback');
    assert.equal(calls[0].options.credentials, 'include');
    assert.equal((calls[0].options.headers as Record<string, string>)['X-Selection-Token'], 'token-1');
    assert.deepEqual(JSON.parse(String(calls[1].options.body)), {
      rating: 5,
      tags: ['服务细致'],
      note: '很好',
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('到店评价使用二维码令牌、幂等键和可选登录身份', async () => {
  const calls: Array<{ url: string; options: RequestInit }> = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input, options = {}) => {
    calls.push({ url: String(input), options });
    return new Response(JSON.stringify({
      id: 8,
      feedback_type: 'visit_feedback',
      rating: 4,
      tags: ['手法专业', '环境舒适'],
      note: '整体不错',
      submitted: true,
      created_at: '2026-09-21T10:00:00Z',
    }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  }) as typeof fetch;

  try {
    const feedback = await submitVisitFeedback({
      visit_feedback_token: 'signed-visit-token',
      rating: 4,
      tags: ['手法专业', '环境舒适'],
      note: '整体不错',
    }, 'intent-key-1234', 'customer-token');

    assert.equal(feedback.feedback_type, 'visit_feedback');
    assert.equal(calls[0].url, '/api/v1/visit-feedback');
    assert.equal(calls[0].options.credentials, 'include');
    assert.deepEqual(calls[0].options.headers, {
      'Content-Type': 'application/json',
      'Idempotency-Key': 'intent-key-1234',
      Authorization: 'Bearer customer-token',
    });
    assert.deepEqual(JSON.parse(String(calls[0].options.body)), {
      visit_feedback_token: 'signed-visit-token',
      rating: 4,
      tags: ['手法专业', '环境舒适'],
      note: '整体不错',
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('匿名到店评价不伪造登录身份', async () => {
  let headers: RequestInit['headers'];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_input, options = {}) => {
    headers = options.headers;
    return new Response(JSON.stringify({
      id: 9, feedback_type: 'visit_feedback', rating: 5, tags: [], note: '', submitted: true, created_at: '2026-09-21T10:00:00Z',
    }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  }) as typeof fetch;
  try {
    await submitVisitFeedback({ visit_feedback_token: 'signed-visit-token', rating: 5, tags: [], note: '' }, 'intent-key-5678');
    assert.equal((headers as Record<string, string>).Authorization, undefined);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

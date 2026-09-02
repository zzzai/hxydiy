import assert from 'node:assert/strict';
import test from 'node:test';

import { getServiceStatus, submitFeedback } from '../src/api.ts';

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

import assert from 'node:assert/strict';
import test from 'node:test';

import { feedbackSourceLabel, feedbackTypeLabel, feedbackUsesServiceLink } from '../src/pages/feedback-page-model.ts';

test('visit feedback is clearly separated from verified service reviews', () => {
  assert.equal(feedbackTypeLabel('visit_feedback'), '到店反馈');
  assert.equal(feedbackSourceLabel({ feedback_type: 'visit_feedback', source: 'personal_qr' }), '服务位二维码');
  assert.equal(feedbackUsesServiceLink({ feedback_type: 'visit_feedback', selection_session_id: null }), false);
});

test('only verified service reviews expose their explicit service reference', () => {
  assert.equal(feedbackTypeLabel('service_review'), '服务评价');
  assert.equal(feedbackSourceLabel({ feedback_type: 'service_review', source: 'completed_service' }), '已完成服务');
  assert.equal(feedbackUsesServiceLink({ feedback_type: 'service_review', selection_session_id: 'session-1' }), true);
  assert.equal(feedbackUsesServiceLink({ feedback_type: 'service_review', selection_session_id: null }), false);
});

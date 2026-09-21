import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

import {
  createVisitFeedbackIntent,
  markVisitFeedbackAttempt,
  shouldRenewVisitFeedbackToken,
  updateVisitFeedbackDraft,
  visitFeedbackErrorMessage,
} from '../src/visitFeedback.ts';

test('弱网重试沿用同一个幂等键，修改内容后创建新意图', () => {
  const keys = ['intent-0001', 'intent-0002'];
  const keyFactory = () => keys.shift() || 'unexpected';
  const initial = createVisitFeedbackIntent(keyFactory);
  const rated = updateVisitFeedbackDraft(initial, { rating: 4, tags: ['环境舒适'], note: '' }, keyFactory);
  const attempted = markVisitFeedbackAttempt(rated);
  const retry = markVisitFeedbackAttempt(attempted);

  assert.equal(retry.idempotencyKey, 'intent-0001');
  const edited = updateVisitFeedbackDraft(retry, { ...retry.draft, note: '整体不错' }, keyFactory);
  assert.equal(edited.idempotencyKey, 'intent-0002');
  assert.equal(edited.attemptedSignature, null);
});

test('常见到店评价错误转换成顾客可执行的提示', () => {
  assert.equal(visitFeedbackErrorMessage({ code: 'FEEDBACK_RATE_LIMITED' }), '提交得有点快，请稍后再试');
  assert.equal(visitFeedbackErrorMessage({ code: 'VISIT_FEEDBACK_TOKEN_INVALID' }), '本次到店信息已变化，请重新扫码后再提交');
  assert.equal(visitFeedbackErrorMessage({ code: 'VISIT_FEEDBACK_TOKEN_EXPIRED' }), '本次到店评价已过期，请重新扫码后再提交');
  assert.equal(visitFeedbackErrorMessage({ code: 'IDEMPOTENCY_KEY_REUSED' }), '评价内容已变化，请再次提交');
  assert.equal(visitFeedbackErrorMessage({ code: 'FEEDBACK_TAG_INVALID' }), '评价选项已更新，请重新选择后提交');
  assert.equal(visitFeedbackErrorMessage({ status: 422 }), '请检查评分、标签数量和留言长度');
});

test('令牌失效或过期时重新获取到店评价令牌', () => {
  assert.equal(shouldRenewVisitFeedbackToken({ code: 'VISIT_FEEDBACK_TOKEN_INVALID' }), true);
  assert.equal(shouldRenewVisitFeedbackToken({ code: 'VISIT_FEEDBACK_TOKEN_EXPIRED' }), true);
  assert.equal(shouldRenewVisitFeedbackToken({ code: 'FEEDBACK_RATE_LIMITED' }), false);
});

test('项目列表首屏常驻评价入口且到店评价不依赖订单', () => {
  const app = fs.readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  assert.match(app, /评价与建议/);
  assert.match(app, /反馈本次到店体验/);
  assert.match(app, /submitVisitFeedback/);
});

test('再次进入项目列表时，待评价服务提供独立的服务评价入口', () => {
  const app = fs.readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  assert.match(app, /serviceFeedbackAction\(Boolean\(serviceStatus\?\.can_evaluate\), Boolean\(serviceStatus\?\.evaluated\)\)/);
  assert.match(app, /serviceFeedbackActionLabel.*onClick=\{openFeedback\}/s);
  assert.match(app, /open=\{feedbackMode === 'service'\}/);
});

test('弱网提交期间冻结评价内容和关闭动作，成功响应不要求再次提交', () => {
  const dialog = fs.readFileSync(new URL('../src/components/FeedbackDialog.tsx', import.meta.url), 'utf8');
  const app = fs.readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  assert.match(dialog, /if \(!submitting\) onClose\(\)/);
  assert.match(dialog, /textarea[^>]*disabled=\{submitting\}/s);
  assert.match(dialog, /aria-label=\{`\$\{value\}星`\}[^>]*disabled=\{submitting\}/s);
  assert.doesNotMatch(app, /登录状态已变化，请再次确认后提交/);
});

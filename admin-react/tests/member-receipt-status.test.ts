import test from 'node:test';
import assert from 'node:assert/strict';
import { receiptAlertTitle, receiptAlertType, receiptBlockedLabel, receiptCurrentLabel, receiptSubmissionLabel } from '../src/pages/memberReceiptStatus.ts';

test('receipt status distinguishes historical blocked reasons and current processing', () => {
  assert.equal(receiptBlockedLabel('blocked_login_required'), '等待重新登录');
  assert.equal(receiptBlockedLabel('blocked_pending_exact_baseline_authorization'), '等待特定授权');
  assert.equal(receiptBlockedLabel('protection_validation_failed'), '保护基线校验未通过');
  assert.equal(receiptBlockedLabel('receipt_conflict'), '证据冲突');
  assert.equal(receiptBlockedLabel(null), '历史未记录');
  assert.equal(receiptCurrentLabel({ latest_attempt: { current_processing: { current_status_label: '已授权，用户要求暂缓' } } }), '已授权，用户要求暂缓');
  assert.match(receiptAlertTitle({ last_success: { successful_submit_at: '2026-11-01T00:00:00Z' }, latest_attempt: { current_processing: { current_status_label: '已授权，用户要求暂缓' } } }), /暂缓/);
});

test('receipt alert never labels a conflict as a trustworthy success', () => {
  assert.equal(receiptAlertType({ has_conflict: true, last_success: { successful_submit_at: '2026-11-01T00:00:00Z' } }), 'error');
  assert.equal(receiptAlertTitle({ has_conflict: true, last_success: { successful_submit_at: '2026-11-01T00:00:00Z' } }), '会员同步回执存在冲突，待核实');
  assert.equal(receiptAlertType({ latest_attempt: { status: 'blocked' } }), 'warning');
  assert.equal(receiptAlertType({ latest_attempt: { status: 'no_new' } }), 'info');
});


test('submission state is tri-state and unknown is not reported as not submitted', () => {
  assert.equal(receiptSubmissionLabel(true), '已提交');
  assert.equal(receiptSubmissionLabel(false), '未提交');
  assert.equal(receiptSubmissionLabel(undefined), '未记录');
  assert.equal(receiptSubmissionLabel(null), '未记录');
});

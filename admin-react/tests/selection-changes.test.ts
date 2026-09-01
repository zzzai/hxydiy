import assert from 'node:assert/strict';
import test from 'node:test';

import { canApproveSelectionChange, canRejectSelectionChange, selectionChangeItemSummary } from '../src/selectionChanges.ts';

test('只有待前台确认的服务中加选可以批准', () => {
  assert.equal(canApproveSelectionChange('awaiting_staff_confirmation'), true);
  assert.equal(canApproveSelectionChange('approved'), false);
  assert.equal(canApproveSelectionChange('rejected'), false);
});

test('只有待前台确认的服务中加选可以拒绝', () => {
  assert.equal(canRejectSelectionChange('awaiting_staff_confirmation'), true);
  assert.equal(canRejectSelectionChange('approved'), false);
  assert.equal(canRejectSelectionChange('rejected'), false);
});

test('加选摘要保留数量和顾客填写的偏好', () => {
  assert.equal(selectionChangeItemSummary({ name: '肩颈加强', quantity: 2, diy_preferences: ['舒缓'] }), '肩颈加强 ×2 · 舒缓');
  assert.equal(selectionChangeItemSummary({ name: '局部调理', quantity: 1, diy_preferences: [] }), '局部调理');
});

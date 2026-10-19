import assert from 'node:assert/strict';
import test from 'node:test';

import { canEditSelection, expiredSelectionCopy, shouldPreserveOccupancyAfterRevision, shouldRecoverPublicDraft } from '../src/selectionFlow.ts';

test('前台确认后的服务中会话允许继续加选', () => {
  assert.equal(canEditSelection('confirmed', 'in_service'), true);
  assert.equal(shouldPreserveOccupancyAfterRevision('in_service'), true);
});

test('已提交等待服务时，顾客返回菜单后允许追加选购', () => {
  assert.equal(canEditSelection('submitted', 'waiting_service'), true);
  assert.equal(canEditSelection('submitted', 'held'), true);
});

test('前台确认但尚未开始服务时不允许顾客覆盖已确认服务项', () => {
  assert.equal(canEditSelection('confirmed', 'waiting_service'), false);
});

test('服务结束、清洁、取消或过期后不允许继续加选', () => {
  assert.equal(canEditSelection('confirmed', 'post_service_present'), false);
  assert.equal(canEditSelection('confirmed', 'cleaning'), false);
  assert.equal(canEditSelection('confirmed', 'released'), false);
  assert.equal(canEditSelection('cancelled', 'in_service'), false);
  assert.equal(canEditSelection('expired', 'in_service'), false);
});

test('服务位释放后提示重新扫码且旧选单保持只读', () => {
  assert.deepEqual(expiredSelectionCopy(), {
    title: '本次位置已释放',
    message: '请重新扫码选择所在位置，或联系前台协助处理。',
  });
  assert.equal(canEditSelection('expired', 'released'), false);
});

test('服务号无座菜单遇到草稿冲突时重建草稿，而不是提示座位已释放', () => {
  assert.equal(shouldRecoverPublicDraft({ status: 409, code: 'CATALOG_VERSION_REQUIRED' }, true), true);
  assert.equal(shouldRecoverPublicDraft({ status: 409, code: 'CURRENT_VERSION_CONFLICT' }, true), true);
  assert.equal(shouldRecoverPublicDraft({ status: 409, code: 'CART_VERSION_CONFLICT' }, true), false);
  assert.equal(shouldRecoverPublicDraft({ status: 409, code: 'CATALOG_VERSION_REQUIRED' }, false), false);
  assert.equal(shouldRecoverPublicDraft({ status: 500 }, true), false);
});

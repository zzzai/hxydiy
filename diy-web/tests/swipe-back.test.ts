import assert from 'node:assert/strict';
import test from 'node:test';

import { isEdgeSwipeBack, shouldReturnToProjectListFromSubmittedScreen } from '../src/swipeBack.ts';
import {
  createOverlayGuardState,
  createOverlayHistoryState,
  createOverlayRootState,
  isOverlayGuardState,
  isOverlayRootState,
  readOverlayHistoryStack,
  readOverlayHistoryState,
  replaceOverlayHistoryState,
  shouldRunDeferredSwipeBack,
} from '../src/overlayHistory.ts';

test('左边缘向右滑动会触发页面内返回', () => {
  assert.equal(isEdgeSwipeBack({ x: 18, y: 240 }, { x: 118, y: 248 }), true);
});

test('非左边缘、距离不足或纵向滑动不会触发返回', () => {
  assert.equal(isEdgeSwipeBack({ x: 54, y: 240 }, { x: 160, y: 246 }), false);
  assert.equal(isEdgeSwipeBack({ x: 18, y: 240 }, { x: 58, y: 244 }), false);
  assert.equal(isEdgeSwipeBack({ x: 18, y: 240 }, { x: 120, y: 304 }), false);
  assert.equal(isEdgeSwipeBack({ x: 18, y: 240 }, { x: 6, y: 242 }), false);
});

test('更短的明确横向手势也能灵敏触发返回', () => {
  assert.equal(isEdgeSwipeBack({ x: 36, y: 240 }, { x: 90, y: 250 }), true);
});

test('提交成功页无弹层时左边缘右滑返回项目列表', () => {
  assert.equal(shouldReturnToProjectListFromSubmittedScreen(
    true,
    false,
    { x: 20, y: 240 },
    { x: 108, y: 248 },
  ), true);
  assert.equal(shouldReturnToProjectListFromSubmittedScreen(
    true,
    true,
    { x: 20, y: 240 },
    { x: 108, y: 248 },
  ), false);
});

test('仅识别荷小悦写入的有效页面层历史状态', () => {
  const state = createOverlayHistoryState({ source: 'entry' }, 'project-detail');

  assert.equal(readOverlayHistoryState(state), 'project-detail');
  assert.equal(readOverlayHistoryState({ hxyDiyOverlay: 'unknown' }), null);
  assert.equal(readOverlayHistoryState({ page: 'project-detail' }), null);
});

test('打开登录页时保留项目详情作为可返回的下层页面', () => {
  const projectDetail = createOverlayHistoryState(null, 'project-detail');
  const couponLogin = createOverlayHistoryState(projectDetail, 'coupon-login');

  assert.deepEqual(readOverlayHistoryStack(projectDetail), ['project-detail']);
  assert.deepEqual(readOverlayHistoryStack(couponLogin), ['project-detail', 'coupon-login']);
});

test('已选清单可作为详情页下层并在返回时恢复', () => {
  const summary = createOverlayHistoryState(null, 'selection-summary');
  const projectDetail = createOverlayHistoryState(summary, 'project-detail');

  assert.deepEqual(readOverlayHistoryStack(projectDetail), ['selection-summary', 'project-detail']);
});

test('登录优惠提示进入手机号登录时替换当前层，不留下重复返回步骤', () => {
  const hint = createOverlayHistoryState(null, 'saving-hint');
  const login = replaceOverlayHistoryState(hint, 'record-login');

  assert.deepEqual(readOverlayHistoryStack(login), ['record-login']);
  assert.equal(readOverlayHistoryState(login), 'record-login');
});

test('DIY 基础页使用双层历史保护，系统返回不会直接退出菜单', () => {
  const root = createOverlayRootState({ source: 'entry' });
  const guard = createOverlayGuardState(root);

  assert.equal(isOverlayRootState(root), true);
  assert.equal(isOverlayGuardState(root), false);
  assert.equal(isOverlayRootState(guard), true);
  assert.equal(isOverlayGuardState(guard), true);
  assert.deepEqual(readOverlayHistoryStack(guard), []);
});

test('原生边缘返回已经退层后，不再执行第二次自定义返回', () => {
  const projectDetail = createOverlayHistoryState(createOverlayGuardState(null), 'project-detail');
  const couponLogin = createOverlayHistoryState(projectDetail, 'coupon-login');

  assert.equal(shouldRunDeferredSwipeBack(couponLogin, couponLogin), true);
  assert.equal(shouldRunDeferredSwipeBack(couponLogin, projectDetail), false);
});

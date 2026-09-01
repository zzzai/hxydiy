import assert from 'node:assert/strict';
import test from 'node:test';

import { getVisibleMenuPaths, isPathAllowed } from '../auth';

test('店长在绑定门店时看到经营、资源、内容、营销、用户和审计菜单但不显示门店主数据', () => {
  const paths = getVisibleMenuPaths('manager', 12);
  assert.ok(paths.includes('/today'));
  assert.ok(paths.includes('/service-positions'));
  assert.ok(paths.includes('/orders'));
  assert.ok(paths.includes('/projects'));
  assert.ok(paths.includes('/users'));
  assert.ok(paths.includes('/audit-logs'));
  assert.equal(paths.includes('/stores'), false);
});

test('绑定门店的店长不能通过地址直接进入门店主数据', () => {
  assert.equal(isPathAllowed('manager', '/stores', 12), false);
  assert.equal(isPathAllowed('manager', '/rooms', 12), true);
});

test('技师不获得店长菜单或桌面管理路由', () => {
  const paths = getVisibleMenuPaths('technician', 12);
  assert.equal(paths.includes('/stores'), false);
  assert.equal(paths.includes('/projects'), false);
  assert.equal(paths.includes('/automation'), false);
  assert.equal(isPathAllowed('technician', '/projects', 12), false);
});

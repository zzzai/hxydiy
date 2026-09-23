import assert from 'node:assert/strict';
import test from 'node:test';

import {
  canManageConfiguration,
  canViewReadOnlyOperations,
  canManageStoreMasterData,
  getDefaultPath,
  getEntryHomePath,
  getEntryLoginPath,
  getPostLoginRedirect,
  getStoreId,
  getVisibleMenuPaths,
  isTechnicianEntry,
  isPathAllowed,
} from '../src/auth.ts';
import { hasPermission } from '../src/core/auth/permissions.ts';


test('staff 只看到门店日常运营页面', () => {
  assert.deepEqual(getVisibleMenuPaths('staff'), [
    '/today',
    '/service-positions',
    '/selection-sessions',
  ]);
});

test('只有普通员工进入只读的今日运营视图', () => {
  assert.equal(canViewReadOnlyOperations('staff'), true);
  assert.equal(canViewReadOnlyOperations('manager'), false);
  assert.equal(canViewReadOnlyOperations('admin'), false);
});

test('staff 不能通过地址直接进入管理员页面', () => {
  assert.equal(isPathAllowed('staff', '/projects'), false);
  assert.equal(isPathAllowed('staff', '/users'), false);
  assert.equal(isPathAllowed('staff', '/orders'), false);
  assert.equal(isPathAllowed('staff', '/rooms/12'), false);
});

test('admin 可以进入全部已注册页面', () => {
  assert.equal(isPathAllowed('admin', '/analytics', 1), true);
  assert.equal(isPathAllowed('admin', '/automation', 1), true);
  assert.equal(isPathAllowed('admin', '/addons'), true);
  assert.equal(isPathAllowed('staff', '/addons'), false);
});

test('店长 manager 与兼容角色 admin 都可以修改门店配置', () => {
  assert.equal(canManageConfiguration('admin'), true);
  assert.equal(canManageConfiguration('manager'), true);
  assert.equal(canManageConfiguration('staff'), false);
  assert.equal(canManageConfiguration(undefined), false);
});

test('店长 manager 看到完整后台菜单并可进入技师管理', () => {
  assert.equal(getVisibleMenuPaths('manager').includes('/techs'), true);
  assert.equal(isPathAllowed('manager', '/techs'), true);
});

test('店长 manager 具备结构化权限层的门店配置权限', () => {
  assert.equal(hasPermission('manager', 'manage_configuration', 12), true);
  assert.equal(hasPermission('staff', 'manage_configuration', 12), false);
});

test('只有不绑定具体门店的总部管理员可以维护门店主数据', () => {
  assert.equal(canManageStoreMasterData('admin', null), true);
  assert.equal(canManageStoreMasterData('admin', 1), false);
  assert.equal(canManageStoreMasterData('staff', null), false);
});

test('未知角色采用最小权限且默认进入今日运营', () => {
  assert.deepEqual(getVisibleMenuPaths('unknown'), []);
  assert.equal(isPathAllowed('unknown', '/today'), false);
  assert.equal(getDefaultPath('unknown'), '/forbidden');
  assert.equal(getDefaultPath('staff'), '/today');
});

test('headquarters only exposes pages backed by headquarters-scoped APIs', () => {
  assert.deepEqual(getVisibleMenuPaths('admin', null), [
    '/audit-logs', '/projects', '/addons', '/products', '/staff-accounts', '/stores',
  ]);
  assert.equal(isPathAllowed('admin', '/techs', null), false);
  assert.equal(isPathAllowed('admin', '/page-content', null), false);
  assert.equal(isPathAllowed('admin', '/users', null), false);
  assert.equal(isPathAllowed('admin', '/automation', null), false);
  assert.equal(isPathAllowed('admin', '/techs', 1), true);
});

test('unbound headquarters admin enters store management instead of store operations', () => {
  assert.equal(getDefaultPath('admin', null), '/stores');
  assert.equal(getDefaultPath('admin', 1), '/today');
});

test('headquarters cannot open store-only operations from a retained URL or sidebar', () => {
  assert.equal(isPathAllowed('admin', '/today', null), false);
  assert.equal(isPathAllowed('admin', '/service-positions', null), false);
  assert.equal(isPathAllowed('admin', '/selection-sessions', null), false);
  assert.equal(isPathAllowed('admin', '/orders', null), false);
  assert.equal(isPathAllowed('admin', '/analytics', null), false);
  assert.equal(isPathAllowed('admin', '/feedback', null), false);
  assert.equal(getVisibleMenuPaths('admin', null).includes('/today'), false);
  assert.equal(isPathAllowed('admin', '/today', 1), true);
  assert.equal(isPathAllowed('admin', '/stores', null), true);
});

test('技师入口使用独立移动路径', () => {
  assert.equal(isTechnicianEntry('/technician/'), true);
  assert.equal(isTechnicianEntry('/technician/today'), true);
  assert.equal(isTechnicianEntry('/admin/'), false);
  assert.equal(getEntryLoginPath(true), '/technician/login');
  assert.equal(getEntryHomePath(true), '/technician/today');
});

test('技师角色不能留在管理后台入口', () => {
  assert.equal(getPostLoginRedirect('/admin/', 'technician'), '/technician/today');
  assert.equal(getPostLoginRedirect('/technician/', 'staff'), '/admin/#/today');
});

test('创建门店资源必须使用登录员工绑定的门店', () => {
  assert.equal(getStoreId({ store_id: 8 }), 8);
  assert.throws(() => getStoreId(null), /未绑定门店/);
  assert.throws(() => getStoreId({ store_id: 0 }), /未绑定门店/);
});

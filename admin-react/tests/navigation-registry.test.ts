import assert from 'node:assert/strict';
import test from 'node:test';

import {
  adminNavigationGroups,
  getNavigationPaths,
  getVisibleNavigationGroups,
} from '../src/core/navigation/index.ts';

test('导航注册表按工作台、门店运营、顾客、服务商品、人员权限、门店资源和系统职责分组', () => {
  assert.deepEqual(adminNavigationGroups.map((group) => group.key), [
    'workbench',
    'operations',
    'customers',
    'catalog',
    'people',
    'store',
    'marketing',
    'system',
  ]);
  assert.deepEqual(
    adminNavigationGroups.find((group) => group.key === 'catalog')?.items.map((item) => item.path),
    ['/projects', '/addons', '/products', '/page-content'],
  );
});

test('导航路径从注册表生成，避免菜单和路由各自维护', () => {
  assert.deepEqual(getNavigationPaths('staff'), [
    '/today',
    '/service-positions',
    '/selection-sessions',
  ]);
  assert.equal(getNavigationPaths('technician').includes('/projects'), false);
});

test('总部管理员可见门店主数据，店长只看到当前门店资源', () => {
  const adminPaths = getVisibleNavigationGroups('admin', null)
    .flatMap((group) => group.items.map((item) => item.path));
  const managerPaths = getVisibleNavigationGroups('manager', 12)
    .flatMap((group) => group.items.map((item) => item.path));
  assert.equal(adminPaths.includes('/stores'), true);
  assert.equal(managerPaths.includes('/stores'), false);
  assert.equal(managerPaths.includes('/techs'), true);
  assert.equal(adminPaths.includes('/staff-accounts'), true);
  assert.equal(managerPaths.includes('/staff-accounts'), false);
  assert.equal(managerPaths.includes('/projects'), true);
  assert.equal(managerPaths.includes('/coupons'), false);
  assert.equal(managerPaths.includes('/automation'), false);
  assert.equal(managerPaths.includes('/page-content'), false);
});

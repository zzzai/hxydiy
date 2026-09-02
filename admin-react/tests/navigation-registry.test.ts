import assert from 'node:assert/strict';
import test from 'node:test';

import {
  adminNavigationGroups,
  getNavigationPaths,
  getVisibleNavigationGroups,
} from '../src/core/navigation/index.ts';

test('导航注册表按运营、服务商品、人员顾客、门店资源和系统职责分组', () => {
  assert.deepEqual(adminNavigationGroups.map((group) => group.key), [
    'operations',
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
    '/orders',
    '/rooms',
    '/techs',
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
});

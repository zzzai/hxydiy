import assert from 'node:assert/strict';
import test from 'node:test';

import {
  CATEGORY_OPTIONS,
  PROJECT_STATUS_OPTIONS,
  canStoreToggleProjectPublication,
  formatProjectPrice,
  normalizeProjectList,
  projectFilterParams,
} from '../src/pages/projects-page-model.ts';

test('项目列表兼容数组和分页响应', () => {
  const item = { id: 1, name: '草本泡脚' };
  assert.deepEqual(normalizeProjectList([item]), { data: [item], total: 1 });
  assert.deepEqual(normalizeProjectList({ items: [item], total: 8 }), { data: [item], total: 8 });
  assert.deepEqual(normalizeProjectList({ data: [item] }), { data: [item], total: 1 });
});

test('项目筛选只提交有值的状态和分类', () => {
  assert.deepEqual(projectFilterParams({ publication_status: 'published', category: 'bath' }), {
    status: 'published', category: 'bath',
  });
  assert.deepEqual(projectFilterParams({ publication_status: '', category: undefined }), {});
});

test('项目价格以元显示并保留两位小数', () => {
  assert.equal(formatProjectPrice(3990), '¥39.90');
  assert.equal(formatProjectPrice(undefined), '-');
});

test('项目分类和状态选项包含正式业务文案', () => {
  assert.equal(CATEGORY_OPTIONS.find((item) => item.value === 'local-strength')?.label, '局部调理');
  assert.equal(PROJECT_STATUS_OPTIONS.find((item) => item.value === 'published')?.label, '已发布');
  assert.equal(PROJECT_STATUS_OPTIONS.find((item) => item.value === 'archived')?.label, '总部强制下线');
});

test('店长只能切换已下发项目的上下架状态，不能恢复总部强制下线项目', () => {
  assert.equal(canStoreToggleProjectPublication('candidate'), true);
  assert.equal(canStoreToggleProjectPublication('published'), true);
  assert.equal(canStoreToggleProjectPublication('inactive'), true);
  assert.equal(canStoreToggleProjectPublication('draft'), false);
  assert.equal(canStoreToggleProjectPublication('archived'), false);
});

test('项目管理页面为总部提供编辑和目标门店选择，为店长只提供上下架入口', async () => {
  const source = await import('node:fs/promises').then((fs) => fs.readFile(new URL('../src/pages/ProjectsPage.tsx', import.meta.url), 'utf8'));
  assert.match(source, /canManageStoreMasterData/);
  assert.match(source, /ProFormSelect name="store_id"/);
  assert.match(source, /店长不能恢复/);
  assert.match(source, /canStoreToggleProjectPublication/);
  assert.match(source, /publication_status === 'archived'/);
  assert.doesNotMatch(source, /const filtered = normalized\.data\.filter/);
  assert.match(source, /total: normalized\.total/);
});

import assert from 'node:assert/strict';
import test from 'node:test';

import { fallbackAttachableAddons, fallbackOptionGroups, withFallbackOptionGroups } from '../src/projectOptionFallbacks.ts';
import type { Addon } from '../src/domain.ts';

test('目录未发布时五类主项目仍提供已确认的必选偏好', () => {
  assert.deepEqual(fallbackOptionGroups('hxy-qiqing-30').map((group) => group.label), ['泡脚液', '手法力度']);
  assert.deepEqual(fallbackOptionGroups('hxy-xiangxiang-60').map((group) => group.label), ['泡脚液', '手法力度', '细节护理']);
  assert.deepEqual(fallbackOptionGroups('hxy-xiaoqi-90').map((group) => group.label), ['泡脚液', '手法力度', '重点调理']);
  assert.deepEqual(fallbackOptionGroups('hxy-tuina-70').map((group) => group.label), ['手法力度']);
  assert.deepEqual(fallbackOptionGroups('hxy-spa-60').map((group) => group.label), ['精油', '手法力度']);
  assert.deepEqual(fallbackOptionGroups('hxy-spa-90').map((group) => group.label), ['精油', '手法力度']);
});

test('无指定父项目的通用加项可挂载到任一主项目', () => {
  const addons = [
    { id: 1, parent_project_id: null, can_attach_to_parent: true },
    { id: 2, parent_project_id: 8, can_attach_to_parent: true },
    { id: 3, parent_project_id: 9, can_attach_to_parent: true },
    { id: 4, parent_project_id: null, can_attach_to_parent: false },
  ] as Addon[];

  assert.deepEqual(fallbackAttachableAddons(addons, 8).map((addon) => addon.id), [1, 2]);
});

test('门店旧配置不完整时补齐缺少的必选组但保留已有选项', () => {
  const spa = withFallbackOptionGroups([
    { label: '精油香型', note: '任选一项', options: ['清润草木'] },
  ], 'hxy-spa-90');

  assert.deepEqual(spa.map((group) => group.label), ['精油香型', '手法力度']);
  assert.deepEqual(spa[0].options, ['清润草木']);
});

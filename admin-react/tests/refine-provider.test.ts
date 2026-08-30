import assert from 'node:assert/strict';
import test from 'node:test';

import { createRefineDataProvider } from '../src/core/dataProvider/refine.ts';

test('Refine getList 将资源和分页映射到现有 AdminDataProvider', async () => {
  const calls: unknown[] = [];
  const provider = createRefineDataProvider({
    getList: async (resource, params) => {
      calls.push({ resource, params });
      return { data: [{ id: 1, name: '项目' }], total: 1 };
    },
  });

  const result = await provider.getList({
    resource: 'projects',
    pagination: { current: 2, pageSize: 20, mode: 'server' },
    filters: [],
    sorters: [],
  });

  assert.deepEqual(calls, [{ resource: 'projects', params: { page: 2, page_size: 20 } }]);
  assert.deepEqual(result, { data: [{ id: 1, name: '项目' }], total: 1 });
});

test('Refine getList 兼容后端 items/total 分页响应', async () => {
  const provider = createRefineDataProvider({
    getList: async () => ({ items: [{ id: 1, name: '一店' }], total: 3 }),
  });

  const result = await provider.getList({
    resource: 'admin/v2/stores',
    pagination: { current: 1, pageSize: 20, mode: 'server' },
    filters: [],
    sorters: [],
  });

  assert.deepEqual(result, { data: [{ id: 1, name: '一店' }], total: 3 });
});

test('Refine create/update 保留变量并返回 data 字段', async () => {
  const calls: unknown[] = [];
  const provider = createRefineDataProvider({
    create: async (resource, input) => { calls.push(['create', resource, input]); return { id: 4, ...input }; },
    update: async (resource, id, input) => { calls.push(['update', resource, id, input]); return { id, ...input }; },
  });

  await provider.create({ resource: 'projects', variables: { name: '新项目' } });
  await provider.update({ resource: 'projects', id: 4, variables: { name: '改名' } });

  assert.deepEqual(calls, [
    ['create', 'projects', { name: '新项目' }],
    ['update', 'projects', 4, { name: '改名' }],
  ]);
});

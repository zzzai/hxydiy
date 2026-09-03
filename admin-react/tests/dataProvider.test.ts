import assert from 'node:assert/strict';
import test from 'node:test';
import { dataProvider, DataProviderError } from '../src/core/dataProvider/index.ts';
import { buildQueryKey } from '../src/core/dataProvider/queryKeys.ts';
import { resources } from '../src/core/resources/index.ts';

function mockAxios(status: number, data: unknown) {
  return { status, data, headers: {}, config: {}, statusText: '' };
}

test('query key 对参数顺序稳定', () => {
  assert.equal(buildQueryKey('rooms', { b: 2, a: 1 }), buildQueryKey('rooms', { a: 1, b: 2 }));
});

test('401/403/409 归一化为 DataProviderError', async () => {
  for (const [status, code] of [[401, 'UNAUTHORIZED'], [403, 'FORBIDDEN'], [409, 'CONFLICT']] as const) {
    const original = dataProvider.request;
    dataProvider.request = async () => { throw { response: mockAxios(status, { detail: 'boom' }) }; };
    await assert.rejects(() => dataProvider.getOne('rooms', 1), (error: unknown) => error instanceof DataProviderError && error.status === status && error.code === code);
    dataProvider.request = original;
  }
});

test('create 发送幂等键且 store_id 不可被输入覆盖', async () => {
  let captured: any;
  const original = dataProvider.request;
  dataProvider.request = async (config: any) => { captured = config; return { data: { id: 1, store_id: 8 } }; };
  dataProvider.setStoreId(8);
  await dataProvider.create('rooms', { name: 'A', store_id: 999 }, 'idem-1');
  assert.equal(captured.headers['X-Idempotency-Key'], 'idem-1');
  assert.equal(captured.data.store_id, 8);
  dataProvider.request = original;
});

test('总部创建目录资源时保留显式选择的目标门店', async () => {
  let captured: any;
  const original = dataProvider.request;
  dataProvider.request = async (config: any) => { captured = config; return { data: { id: 1, store_id: 12 } }; };
  dataProvider.setStoreId(null);
  await dataProvider.create('admin/v2/products', { name: '总部商品', store_id: 12 });
  assert.equal(captured.data.store_id, 12);
  dataProvider.request = original;
});

test('update 传递版本并缓存失效', async () => {
  let captured: any;
  const original = dataProvider.request;
  dataProvider.request = async (config: any) => { captured = config; return { data: { id: 1, store_id: 8 } }; };
  dataProvider.setStoreId(8);
  await dataProvider.update('rooms', 1, { name: 'B', store_id: 999 }, 3);
  assert.equal(captured.headers['If-Match'], '3');
  assert.equal(captured.data.store_id, 8);
  dataProvider.request = original;
});

test('更新不应向严格资源负载隐式注入 store_id', async () => {
  let captured: any;
  const original = dataProvider.request;
  dataProvider.request = async (config: any) => { captured = config; return { data: { ok: true } }; };
  dataProvider.setStoreId(8);
  await dataProvider.update('admin/v2/projects', 1, { name: '只改名称' });
  assert.deepEqual(captured.data, { name: '只改名称' });
  dataProvider.request = original;
});

test('serviceOrders 资源键可通过 getList 请求服务单', async () => {
  assert.equal(resources.serviceOrders, 'operations/live-board');
  let captured: any;
  const original = dataProvider.request;
  dataProvider.request = async (config: any) => {
    captured = config;
    return { data: { items: [] } };
  };
  await dataProvider.getList(resources.serviceOrders, { status: '__service_orders_test__' });
  assert.equal(captured.url, resources.serviceOrders);
  assert.deepEqual(captured.params, { status: '__service_orders_test__' });
  dataProvider.request = original;
});

test('切换门店或重新登录时不会复用上一会话的列表缓存', async () => {
  let requests = 0;
  const original = dataProvider.request;
  dataProvider.request = async () => ({ data: { store_id: ++requests } });
  dataProvider.setStoreId(101);
  const first = await dataProvider.getList<{ store_id: number }>('store-switch-test', { page: 1 });
  dataProvider.setStoreId(202);
  const second = await dataProvider.getList<{ store_id: number }>('store-switch-test', { page: 1 });
  assert.equal(first.store_id, 1);
  assert.equal(second.store_id, 2);
  assert.equal(requests, 2);
  dataProvider.request = original;
});

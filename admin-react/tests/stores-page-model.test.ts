import assert from 'node:assert/strict';
import test from 'node:test';

import {
  getStoreStatusMeta,
  normalizeStoreList,
  type Store,
} from '../src/pages/stores-page-model.ts';

test('门店状态使用统一中文文案和语义色', () => {
  assert.deepEqual(getStoreStatusMeta('open'), { label: '营业中', color: 'green' });
  assert.deepEqual(getStoreStatusMeta('preparing'), { label: '筹备中', color: 'gold' });
  assert.deepEqual(getStoreStatusMeta('closed'), { label: '已停业', color: 'default' });
});

test('门店列表兼容 Refine 返回的 data/total 结构', () => {
  const stores: Store[] = [{
    id: 1,
    store_code: 'store-01',
    name: '荷小悦一店',
    city: '北京',
    address: '朝阳区',
    phone: '010-12345678',
    business_hours: '10:00-22:00',
    status: 'open',
  }];
  assert.deepEqual(normalizeStoreList({ data: stores, total: 4 }), { data: stores, total: 4 });
});

import assert from 'node:assert/strict';
import test from 'node:test';

import {
  formatProductPrice,
  normalizeProductList,
  toProductPayload,
} from '../src/pages/products-page-model.ts';

test('商品列表兼容数组和 Refine 分页结构', () => {
  const product = { id: 1, name: '泡脚包', price_cents: 990 } as never;
  assert.deepEqual(normalizeProductList([product]), { data: [product], total: 1 });
  assert.deepEqual(normalizeProductList({ items: [product], total: 4 }), { data: [product], total: 4 });
});

test('商品价格按元转换为分并强制使用当前门店', () => {
  assert.deepEqual(toProductPayload({ code: 'foot-1', price: 9.9, store_id: 99 }, 12), {
    code: 'foot-1', store_id: 12, price_cents: 990, image_url: '',
  });
  assert.equal(formatProductPrice(990), '¥9.90');
});

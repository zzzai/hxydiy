import assert from 'node:assert/strict';
import test from 'node:test';

import {
  formatProductPrice,
  canStoreToggleProductPublication,
  normalizeProductList,
  productToForm,
  toProductUpdatePayload,
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

test('商品记录可还原为编辑表单并将分转换为元', () => {
  assert.deepEqual(productToForm({
    id: 7,
    store_id: 12,
    code: 'foot-7',
    name: '草本泡脚包',
    desc: '舒缓放松',
    spec: '1包',
    product_type: 'foot',
    price_cents: 1299,
    image_url: 'https://cdn.example/foot-7.jpg',
    publication_status: 'published',
  }), {
    code: 'foot-7',
    name: '草本泡脚包',
    desc: '舒缓放松',
    spec: '1包',
    product_type: 'foot',
    price: 12.99,
    image_url: 'https://cdn.example/foot-7.jpg',
    publication_status: 'published',
  });
});

test('商品更新负载不带 store_id，避免编辑时越权改门店归属', () => {
  assert.deepEqual(toProductUpdatePayload({
    code: 'foot-7', name: '新名称', price: 10.5, store_id: 999,
  }), {
    code: 'foot-7', name: '新名称', price_cents: 1050, image_url: '',
  });
});

test('商品管理页面提供编辑和店长上下架入口', async () => {
  const source = await import('node:fs/promises').then((fs) => fs.readFile(new URL('../src/pages/ProductsPage.tsx', import.meta.url), 'utf8'));
  assert.match(source, /EditOutlined/);
  assert.match(source, /publication_status/);
  assert.match(source, /Switch/);
  assert.match(source, /refineDataProvider\.update/);
  assert.match(source, /强制下线/);
  assert.match(source, /publication_status === 'archived'/);
  assert.match(source, /canStoreToggleProductPublication/);
});

test('店长只能切换已下发目录的上架状态，不能恢复总部归档商品', () => {
  assert.equal(canStoreToggleProductPublication('candidate'), true);
  assert.equal(canStoreToggleProductPublication('published'), true);
  assert.equal(canStoreToggleProductPublication('inactive'), true);
  assert.equal(canStoreToggleProductPublication('draft'), false);
  assert.equal(canStoreToggleProductPublication('archived'), false);
});

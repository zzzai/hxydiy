import assert from 'node:assert/strict';
import test from 'node:test';

import { getStoreContextLabel } from '../core/auth/storeContext';
import { DEFAULT_SERVICE_POSITION_LAYOUT, normalizeServicePositions } from '../servicePositions';

test('当前门店上下文显示门店名称而不是切店控件', () => {
  assert.equal(getStoreContextLabel({ store_id: 12, store_name: '望京店' }), '望京店');
  assert.equal(getStoreContextLabel({ store_id: 12 }), '当前门店');
});

test('未绑定门店的总部管理员显示总部上下文', () => {
  assert.equal(getStoreContextLabel({ role: 'admin', store_id: null }), '总部');
});

test('服务位看板补齐固定的 8 个大厅沙发和 9 个房间床位', () => {
  assert.equal(DEFAULT_SERVICE_POSITION_LAYOUT.length, 17);
  const positions = normalizeServicePositions([]);
  assert.equal(positions.length, 17);
  assert.equal(positions.filter((item) => item.type === 'sofa').length, 8);
  assert.equal(positions.filter((item) => item.type === 'bed').length, 9);
});

import assert from 'node:assert/strict';
import test from 'node:test';

import { addonFormPayload, addonToForm } from '../src/addonContent.ts';

test('收费加项把元价格转换为分并保留会员价开关', () => {
  const payload = addonFormPayload({ chargeable: true, store_price: 12, member_price: 8, member_price_enabled: true });
  assert.equal(payload.store_price_cents, 1200);
  assert.equal(payload.member_price_cents, 800);
  assert.equal(payload.member_price_enabled, true);
});

test('免费选项不会提交任何价格或会员价开关', () => {
  const payload = addonFormPayload({ chargeable: false, store_price: 12, member_price: 8, member_price_enabled: true });
  assert.equal(payload.store_price_cents, 0);
  assert.equal(payload.member_price_cents, null);
  assert.equal(payload.member_price_enabled, false);
});

test('加项数据可以回填为元单位表单', () => {
  const form = addonToForm({ store_price_cents: 1200, member_price_cents: 800, member_price_enabled: true });
  assert.equal(form.store_price, 12);
  assert.equal(form.member_price, 8);
});

test('编辑时清除关联主项目会显式提交 null', () => {
  const payload = addonFormPayload({ chargeable: true, store_price: 12, parent_project_id: undefined });
  assert.equal(payload.parent_project_id, null);
  assert.match(JSON.stringify(payload), /"parent_project_id":null/);
});

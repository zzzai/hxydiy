import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { canEditAddonMasterData, canStoreToggleAddon, canViewAddons, addonCreateStoreId, validateAddonPrices } from '../src/pages/addon-page-model.ts';
import { isNavigationPathAllowed } from '../src/core/navigation/index.ts';

test('总部管理员可访问并编辑加项主数据，店长只能访问', () => {
  assert.equal(canViewAddons('admin'), true);
  assert.equal(canEditAddonMasterData('admin', null), true);
  assert.equal(canEditAddonMasterData('manager', 1), false);
});

test('普通员工无权访问加项，店长不能恢复总部强制下线', () => {
  assert.equal(canViewAddons('staff'), false);
  assert.equal(isNavigationPathAllowed('staff', '/addons', 1), false);
  assert.equal(isNavigationPathAllowed('manager', '/addons', 1), true);
  assert.equal(canStoreToggleAddon('archived'), false);
  assert.equal(canStoreToggleAddon('candidate'), true);
});

test('总部创建加项必须选择目标门店，店长使用绑定门店', () => {
  assert.throws(() => addonCreateStoreId('admin', null, null), /目标门店/);
  assert.equal(addonCreateStoreId('admin', null, 3), 3);
  assert.equal(addonCreateStoreId('manager', 2, null), 2);
});

test('加项价格校验门店价、会员价及会员价上限', () => {
  assert.match(validateAddonPrices({ chargeable: true, store_price: null }) || '', /门店价/);
  assert.match(validateAddonPrices({ chargeable: true, store_price: 10, member_price_enabled: true, member_price: null }) || '', /会员价/);
  assert.match(validateAddonPrices({ chargeable: true, store_price: 10, member_price_enabled: true, member_price: 12 }) || '', /高于/);
  assert.equal(validateAddonPrices({ chargeable: false, store_price: null }), null);
});

test('加项页面使用 ProComponents、统一数据提供器并保留媒体上传', () => {
  const source = readFileSync(new URL('../src/pages/AddonsPage.tsx', import.meta.url), 'utf8');
  assert.match(source, /ProTable/);
  assert.match(source, /ModalForm/);
  assert.match(source, /refineDataProvider/);
  assert.match(source, /MediaUploadField/);
  assert.match(source, /total:\s*result\.total/);
  assert.match(source, /storeId=/);
});

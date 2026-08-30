import assert from 'node:assert/strict';
import test from 'node:test';

import {
  calculatePreviewPricing,
  calculateDetailPreviewPricing,
  emptyPricingPreview,
  canCustomerChangePosition,
  isCatalogOptionsProject,
  isDetailOnlyProject,
  isFootbathOptionsProject,
  priceGuidance,
  priceGuidanceForPrices,
  detailPreviewProjectIds,
  detailPreviewLocalParts,
  previewPriceForIdentity,
  detailPriceComparison,
  resolveMemberTotalCents,
  detailBasePriceComparison,
  projectCatalogBadge,
  projectTagLabel,
  supportsFootBathBundle,
  CATALOG_SECTIONS,
  displayProjectName,
  projectListPricePresentation,
  projectImage,
  mergeSubmittedSelectionItems,
  type Project,
} from '../src/domain.ts';
import * as domainModule from '../src/domain.ts';

function project(partial: Partial<Project> & Pick<Project, 'id' | 'code' | 'category'>): Project {
  return {
    name: partial.code, summary: '', duration_min: 30, publication_status: 'published',
    image_url: '', tags: [], prices: [
      { price_type: 'store', amount_cents: 3990 },
      { price_type: 'member', amount_cents: 2990 },
    ],
    ...partial,
  } as Project;
}

test('提交后返回菜单追加项目时保留原已提交项目', () => {
  const original = [{
    project_id: 1, quantity: 1, addon_ids: [], diy_preferences: ['适中力度'], item_type: 'service' as const, chargeable: true,
  }];
  const added = [{
    project_id: 2, quantity: 1, addon_ids: [], diy_preferences: ['标准流程'], item_type: 'service' as const, chargeable: true,
  }];
  const merged = mergeSubmittedSelectionItems(original, added);
  assert.equal(merged.length, 2);
  assert.deepEqual(merged.map((item) => item.project_id), [1, 2]);
});

test('追加同配置项目累加数量，不同偏好保留独立服务行', () => {
  const base = [{
    project_id: 1, quantity: 1, addon_ids: [11], diy_preferences: ['适中力度'], item_type: 'service' as const, chargeable: true,
  }];
  const added = [
    { project_id: 1, quantity: 2, addon_ids: [11], diy_preferences: ['适中力度'], item_type: 'service' as const, chargeable: true },
    { project_id: 1, quantity: 1, addon_ids: [11], diy_preferences: ['轻柔力度'], item_type: 'service' as const, chargeable: true },
  ];
  const merged = mergeSubmittedSelectionItems(base, added);
  assert.equal(merged.length, 2);
  assert.equal(merged.find((item) => item.diy_preferences[0] === '适中力度')?.quantity, 3);
  assert.equal(merged.find((item) => item.diy_preferences[0] === '轻柔力度')?.quantity, 1);
});

test('追加新茶饮替换原茶饮，其他已提交服务不受影响', () => {
  const base = [
    { project_id: 1, quantity: 1, addon_ids: [], diy_preferences: [], item_type: 'service' as const, chargeable: true },
    { project_id: 'tea', quantity: 1, addon_ids: [], diy_preferences: ['老姜茶'], item_type: 'preference' as const, chargeable: false },
  ];
  const added = [{
    project_id: 'tea', quantity: 1, addon_ids: [], diy_preferences: ['玫瑰茶'], item_type: 'preference' as const, chargeable: false,
  }];
  const merged = mergeSubmittedSelectionItems(base, added);
  assert.deepEqual(merged.map((item) => item.project_id), [1, 'tea']);
  assert.deepEqual(merged.find((item) => item.project_id === 'tea')?.diy_preferences, ['玫瑰茶']);
});

test('顾客端分类导航保留六个品牌分类并将局部调理并入养生小项', () => {
  assert.deepEqual(CATALOG_SECTIONS.map((section) => section.id), ['tea', 'bath', 'balance', 'care', 'small', 'kit']);
  assert.equal(CATALOG_SECTIONS.find((section) => section.id === 'small')?.label, '更多服务');
  assert.deepEqual(CATALOG_SECTIONS.find((section) => section.id === 'small')?.categories, ['small', 'local-strength']);
  assert.equal(CATALOG_SECTIONS.find((section) => section.id === 'kit')?.label, '功夫套盒');
});

test('两个 SPA 使用可区分的顾客名称', () => {
  assert.equal(displayProjectName(project({ id: 60, code: 'hxy-spa-60', category: 'care', name: '精油SPA' })), '舒享精油 SPA');
  assert.equal(displayProjectName(project({ id: 90, code: 'hxy-spa-90', category: 'care', name: '精油SPA' })), '深享精油 SPA');
});

test('局部推拿使用最新菜单中的顾客名称', () => {
  assert.equal(displayProjectName(project({ id: 11, code: 'hxy-jubu-30', category: 'local-strength', name: '局部推拿' })), '局部推拿');
});

test('足部精修使用专属荷小悦主图资源', () => {
  const item = project({ id: 14, code: 'hxy-foot-refine-1', category: 'small', name: '足部精修' });
  assert.match(projectImage(item), /projects\/hxy-foot-refine-1\.webp$/);
});

test('项目列表价格单行突出会员价且不使用门店价和可省文案', () => {
  const item = project({ id: 1, code: 'hxy-qiqing-30', category: 'bath' });
  assert.deepEqual(projectListPricePresentation(item, null), {
    primaryCents: 3990,
    primaryPrefix: '',
    secondaryCents: 2990,
    secondaryPrefix: '会员',
    secondaryStrikethrough: false,
  });
  assert.deepEqual(projectListPricePresentation(item, { is_member: false }), {
    primaryCents: 3990,
    primaryPrefix: '',
    secondaryCents: 2990,
    secondaryPrefix: '会员',
    secondaryStrikethrough: false,
  });
  assert.deepEqual(projectListPricePresentation(item, { is_member: true }), {
    primaryCents: 2990,
    primaryPrefix: '会员',
    secondaryCents: 3990,
    secondaryPrefix: '',
    secondaryStrikethrough: true,
  });
});

test('详情页按当前身份读取包含加购后的实时预估价', () => {
  const preview = {
    storeTotalCents: 12800,
    memberTotalCents: 10800,
  } as Parameters<typeof previewPriceForIdentity>[0];
  assert.equal(previewPriceForIdentity(preview, false), 12800);
  assert.equal(previewPriceForIdentity(preview, true), 10800);
});

test('详情页门店价和会员价都来自当前项目配置预估，不回退到项目基础价', () => {
  assert.deepEqual(detailPriceComparison({ storeTotalCents: 22700, memberTotalCents: 15700 }, true), {
    currentCents: 15700,
    currentLabel: '会员价',
    comparisonCents: 22700,
    comparisonLabel: '门店价',
  });
  assert.deepEqual(detailPriceComparison({ storeTotalCents: 22700, memberTotalCents: 15700 }, false), {
    currentCents: 22700,
    currentLabel: '门店价',
    comparisonCents: 15700,
    comparisonLabel: '会员价',
  });
});

test('无促销时会员总价优先采用快照会员明细小计，避免异常顶层字段显示成67元', () => {
  assert.equal(resolveMemberTotalCents({
    store_total_cents: 61300,
    member_total_cents: 6700,
    member_subtotal_cents: 41300,
    promotion_code: '',
  }, 6700), 41300);
});

test('存在促销时保留快照最终会员总价，不用明细小计覆盖已减免金额', () => {
  assert.equal(resolveMemberTotalCents({
    member_total_cents: 9800,
    member_subtotal_cents: 12790,
    promotion_code: 'FOOT_BATH_TWO_LOCAL',
  }, 9800), 9800);
});

test('详情页主价格始终是当前项目基础门店价与会员价，不包含已选加购合计', () => {
  const current = project({ id: 2, code: 'hxy-xiangxiang-60', category: 'bath', prices: [
    { price_type: 'store', amount_cents: 8900 },
    { price_type: 'member', amount_cents: 6900 },
  ] });
  assert.deepEqual(detailBasePriceComparison(current, true), {
    currentCents: 6900,
    currentLabel: '会员价',
    comparisonCents: 8900,
    comparisonLabel: '门店价',
  });
  assert.deepEqual(detailBasePriceComparison(current, false), {
    currentCents: 8900,
    currentLabel: '门店价',
    comparisonCents: 6900,
    comparisonLabel: '会员价',
  });
});

test('二维码绑定服务位后顾客不能自行调整沙发位', () => {
  assert.equal(canCustomerChangePosition('personal_qr', 'sofa', 'held'), false);
  assert.equal(canCustomerChangePosition('personal_qr', 'sofa', 'waiting_service'), false);
  assert.equal(canCustomerChangePosition('personal_qr', 'sofa', 'in_service'), false);
  assert.equal(canCustomerChangePosition('kiosk', 'sofa', 'held'), false);
  assert.equal(canCustomerChangePosition('personal_qr', 'room', 'held'), false);
});

test('套盒是固定详情项目，不进入顾客选购和 DIY 配置', () => {
  const kit = { category: 'kit' };
  const service = { category: 'balance' };

  assert.equal(isDetailOnlyProject(kit), true);
  assert.equal(isDetailOnlyProject(service), false);
  assert.equal(projectCatalogBadge(kit), '套盒服务');
  assert.equal(projectCatalogBadge(service), '可加选服务');
});

test('养生小项使用顾客易懂的服务标签，不显示内部分类词', () => {
  const small = { category: 'small', code: 'hxy-caier-30' };

  assert.equal(projectCatalogBadge(small), '特色服务');
  assert.equal(isDetailOnlyProject(small), false);
  assert.equal(projectTagLabel('小项'), '');
  assert.equal(projectTagLabel('按次'), '单次服务');
  assert.equal(projectTagLabel('可按需加选'), '');
  assert.equal(projectTagLabel('利润款'), '');
});

test('历史误分类为 balance 的套盒编码 hxy-taoke-60 仍识别为固定套盒', () => {
  const legacyKit = { category: 'balance', code: 'hxy-taoke-60' };
  const normalBalance = { category: 'balance', code: 'hxy-tuina-70' };

  assert.equal(isDetailOnlyProject(legacyKit), true);
  assert.equal(isDetailOnlyProject(normalBalance), false);
  assert.equal(projectCatalogBadge(legacyKit), '套盒服务');
  assert.equal(projectCatalogBadge(normalBalance), '可加选服务');
});

test('两项局部调理时泡脚费按价格带全额减免', () => {
  const footBath = project({ id: 1, code: 'hxy-qiqing-30', category: 'bath', prices: [
    { price_type: 'store', amount_cents: 3990 }, { price_type: 'member', amount_cents: 2990 },
  ] });
  const local = project({ id: 2, code: 'hxy-jubu-30', category: 'local-strength', prices: [
    { price_type: 'store', amount_cents: 6900 }, { price_type: 'member', amount_cents: 4900 },
  ] });
  const preview = calculatePreviewPricing({
    projects: [footBath, local],
    selectedProjectIds: [1],
    localParts: ['肩颈', '腿部'],
    projectAddonIds: {},
    addons: [],
  });

  assert.equal(preview.qualified, true);
  assert.equal(preview.storeAdjustmentCents, -3990);
  assert.equal(preview.memberAdjustmentCents, -2990);
  assert.equal(preview.storeTotalCents, 13800);
  assert.equal(preview.memberTotalCents, 9800);
});

test('三个沐足项目共享目录选项但只有 39.9 泡脚支持组合减免', () => {
  const testProject = (code: string) => ({ code } as Project);

  assert.equal(isFootbathOptionsProject(testProject('hxy-qiqing-30')), true);
  assert.equal(isFootbathOptionsProject(testProject('hxy-xiangxiang-60')), true);
  assert.equal(isFootbathOptionsProject(testProject('hxy-xiaoqi-90')), true);
  assert.equal(isFootbathOptionsProject(testProject('hxy-tuina-70')), false);
  assert.equal(supportsFootBathBundle(testProject('hxy-qiqing-30')), true);
  assert.equal(supportsFootBathBundle(testProject('hxy-xiangxiang-60')), false);
  assert.equal(supportsFootBathBundle(testProject('hxy-xiaoqi-90')), false);
});

test('泡脚、推拿和 SPA 都使用发布目录但只有泡脚项目显示局部加强', () => {
  const testProject = (code: string) => ({ code } as Project);

  for (const code of ['hxy-qiqing-30', 'hxy-xiangxiang-60', 'hxy-xiaoqi-90', 'hxy-tuina-70', 'hxy-spa-60', 'hxy-spa-90']) {
    assert.equal(isCatalogOptionsProject(testProject(code)), true, code);
  }
  assert.equal(isCatalogOptionsProject(testProject('hxy-taoke-60')), false);
  assert.equal(isFootbathOptionsProject(testProject('hxy-tuina-70')), false);
  assert.equal(isFootbathOptionsProject(testProject('hxy-spa-90')), false);
});

test('60 分钟和 90 分钟沐足即使选两个不同局部也不减泡脚基础费', () => {
  const local = project({ id: 2, code: 'hxy-jubu-30', category: 'local-strength', prices: [
    { price_type: 'store', amount_cents: 6900 }, { price_type: 'member', amount_cents: 4900 },
  ] });
  for (const code of ['hxy-xiangxiang-60', 'hxy-xiaoqi-90']) {
    const footBath = project({ id: 1, code, category: 'bath', prices: [
      { price_type: 'store', amount_cents: 6990 }, { price_type: 'member', amount_cents: 5990 },
    ] });
    const preview = calculatePreviewPricing({
      projects: [footBath, local], selectedProjectIds: [1], localParts: ['肩颈', '腿部'], projectAddonIds: {}, addons: [],
    });

    assert.equal(preview.qualified, false);
    assert.equal(preview.storeAdjustmentCents, 0);
    assert.equal(preview.memberAdjustmentCents, 0);
    assert.equal(preview.storeTotalCents, 20790);
    assert.equal(preview.memberTotalCents, 15790);
  }
});

test('重复或空白局部部位不会触发泡脚组合减免', () => {
  const footBath = project({ id: 1, code: 'hxy-qiqing-30', category: 'bath' });
  const local = project({ id: 2, code: 'hxy-jubu-30', category: 'local-strength', prices: [
    { price_type: 'store', amount_cents: 6900 }, { price_type: 'member', amount_cents: 4900 },
  ] });
  const preview = calculatePreviewPricing({
    projects: [footBath, local], selectedProjectIds: [1], localParts: [' 肩颈 ', '肩颈', '   '], projectAddonIds: {}, addons: [],
  });

  assert.equal(preview.qualified, false);
  assert.equal(preview.storeAdjustmentCents, 0);
  assert.equal(preview.memberAdjustmentCents, 0);
  assert.equal(preview.storeTotalCents, 24690);
  assert.equal(preview.memberTotalCents, 17690);
});

test('单项局部调理不减泡脚费', () => {
  const footBath = project({ id: 1, code: 'hxy-qiqing-30', category: 'bath', prices: [
    { price_type: 'store', amount_cents: 3990 }, { price_type: 'member', amount_cents: 2990 },
  ] });
  const local = project({ id: 2, code: 'hxy-jubu-30', category: 'local-strength', prices: [
    { price_type: 'store', amount_cents: 6900 }, { price_type: 'member', amount_cents: 4900 },
  ] });
  const preview = calculatePreviewPricing({
    projects: [footBath, local],
    selectedProjectIds: [1],
    localParts: ['肩颈'],
    projectAddonIds: {},
    addons: [],
  });

  assert.equal(preview.qualified, false);
  assert.equal(preview.storeTotalCents, 3990 + 6900);
});

test('可编辑选单优先显示本地实时预计金额，确认后才使用门店冻结金额', () => {
  const displayPayableTotal = (
    domainModule as typeof domainModule & {
      displayPayableTotal?: (input: {
        readOnly: boolean;
        serverTotalCents: number | null;
        previewStoreTotalCents: number;
        previewMemberTotalCents: number;
        priceType: 'store' | 'member';
      }) => number;
    }
  ).displayPayableTotal;
  assert.equal(typeof displayPayableTotal, 'function');
  if (!displayPayableTotal) return;

  const input = {
    serverTotalCents: 20700,
    previewStoreTotalCents: 27600,
    previewMemberTotalCents: 19600,
    priceType: 'store' as const,
  };
  assert.equal(displayPayableTotal({ ...input, readOnly: false }), 27600);
  assert.equal(displayPayableTotal({ ...input, readOnly: true }), 20700);
  assert.equal(displayPayableTotal({ ...input, readOnly: true, serverTotalCents: null }), 27600);
});

test('未登录显示门店价并引导登录看会员价', () => {
  const item = project({ id: 1, code: 'hxy-qiqing-30', category: 'bath' });
  const guidance = priceGuidance(item, null);
  assert.equal(guidance.primaryLabel, '门店价');
  assert.equal(guidance.primaryCents, 3990);
  assert.equal(guidance.memberHintCents, 2990);
  assert.equal(guidance.hintAction, 'login');
  assert.match(guidance.hintText, /登录享会员价/);
});

test('已登录非会员显示门店价并引导办卡', () => {
  const item = project({ id: 1, code: 'hxy-qiqing-30', category: 'bath' });
  const guidance = priceGuidance(item, { is_member: false });
  assert.equal(guidance.primaryLabel, '门店价');
  assert.equal(guidance.hintAction, 'card');
  assert.match(guidance.hintText, /办卡享会员价/);
});

test('会员直接显示会员价并划线门店价', () => {
  const item = project({ id: 1, code: 'hxy-qiqing-30', category: 'bath' });
  const guidance = priceGuidance(item, { is_member: true });
  assert.equal(guidance.primaryLabel, '会员价');
  assert.equal(guidance.primaryCents, 2990);
  assert.equal(guidance.strikethroughCents, 3990);
  assert.equal(guidance.hintAction, null);
});

test('详情页预览只计算当前项目及其关联小项，不带入其他已选主项目', () => {
  assert.deepEqual(detailPreviewProjectIds(2, [8, 8, 9]), [2, 8, 9]);
});

test('详情页仅对支持局部加强的泡脚项目计入局部部位价格', () => {
  assert.deepEqual(detailPreviewLocalParts(project({ id: 1, code: 'hxy-spa-90', category: 'care' }), ['肩颈']), []);
  assert.deepEqual(detailPreviewLocalParts(project({ id: 2, code: 'hxy-qiqing-30', category: 'bath' }), ['肩颈']), ['肩颈']);
});

test('详情页预览隔离整单：其他已选项目及其加购不应进入当前项目价格', () => {
  const current = project({ id: 2, code: 'hxy-qiqing-30', category: 'bath' });
  const other = project({ id: 8, code: 'hxy-spa-90', category: 'care', prices: [{ price_type: 'store', amount_cents: 19900 }, { price_type: 'member', amount_cents: 13900 }] });
  const addon = { id: 99, code: 'other-addon', name: '其他项目加购', parent_project_id: other.id, duration_min: 15, summary: '', image_url: '', display_order: 1, chargeable: true, independently_sellable: false, can_attach_to_parent: true, prices: { store: 3900, member: 2900 } };
  const preview = calculateDetailPreviewPricing({ project: current, projects: [current, other], addons: [addon], addonIds: [], localParts: [] });
  assert.equal(preview.storeTotalCents, 3990);
  assert.equal(preview.memberTotalCents, 2990);
});

test('详情页尚未绑定项目时返回安全空预览，不因读取项目ID导致白屏', () => {
  assert.deepEqual(emptyPricingPreview(), {
    storeSubtotalCents: 0,
    memberSubtotalCents: 0,
    storeAdjustmentCents: 0,
    memberAdjustmentCents: 0,
    storeTotalCents: 0,
    memberTotalCents: 0,
    qualified: false,
  });
});

test('非会员加购项显示门店价并提示办理年卡可享会员价', () => {
  const guidance = priceGuidanceForPrices(3900, 2900, { is_member: false });
  assert.equal(guidance.primaryCents, 3900);
  assert.equal(guidance.memberHintCents, 2900);
  assert.equal(guidance.hintAction, 'card');
  assert.match(guidance.hintText, /办卡享会员价/);
});

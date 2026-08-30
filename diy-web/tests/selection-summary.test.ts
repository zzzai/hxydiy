import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildSelectionItems,
  calculatePreviewPricing,
  type Addon,
  type PricingPreview,
  type Project,
} from '../src/domain.ts';
import * as selectionSummaryModule from '../src/selectionSummary.ts';
import {
  activePromotion,
  buildSelectionSummary,
  countSelectionDraft,
  emptySelectionDraft,
  removeSelectionEntry,
  type SelectionDraft,
} from '../src/selectionSummary.ts';

test('已提交返回项目菜单时使用空白选购草稿', () => {
  assert.deepEqual(emptySelectionDraft(), {
    selectedProjectIds: [],
    projectPreferences: {},
    projectAddonIds: {},
    projectCatalogSelections: {},
    localParts: [],
    tea: null,
  });
});

function project(partial: Partial<Project> & Pick<Project, 'id' | 'code' | 'category' | 'name'>): Project {
  return {
    category_mark: '泡',
    duration_min: 30,
    summary: '',
    image_url: '',
    tags: [],
    price_label: '',
    prices: [
      { price_type: 'store', amount_cents: 3990 },
      { price_type: 'member', amount_cents: 2990 },
    ],
    ...partial,
  };
}

const footBath = project({ id: 1, code: 'hxy-qiqing-30', category: 'bath', name: '草本泡脚' });
const local = project({
  id: 2,
  code: 'hxy-jubu-30',
  category: 'local-strength',
  name: '局部调理',
  prices: [
    { price_type: 'store', amount_cents: 6900 },
    { price_type: 'member', amount_cents: 4900 },
  ],
});
const addon: Addon = {
  id: 11,
  code: 'addon-yanhu',
  name: '眼部热敷',
  parent_project_id: 1,
  duration_min: 15,
  summary: '服务中可加选',
  image_url: '',
  display_order: 1,
  chargeable: true,
  independently_sellable: false,
  can_attach_to_parent: true,
  prices: { store: 1200, member: 800 },
};

function draft(overrides: Partial<SelectionDraft> = {}): SelectionDraft {
  return {
    selectedProjectIds: [1],
    projectPreferences: { 1: ['适中'] },
    projectAddonIds: { 1: [11] },
    localParts: ['肩颈', '腿部'],
    tea: '老姜茶',
    ...overrides,
  };
}

test('清单按主项目、挂载加项、局部调理和赠饮生成可操作条目', () => {
  const summary = buildSelectionSummary({
    projects: [footBath, local],
    addons: [addon],
    draft: draft(),
    isMember: true,
  });

  assert.equal(summary.totalCount, 5);
  assert.deepEqual(summary.groups.map((item) => item.kind), ['project', 'local', 'local', 'tea']);
  assert.equal(summary.groups[0].title, '草本泡脚');
  assert.equal(summary.groups[0].detail, '适中');
  assert.equal(summary.groups[0].priceCents, 2990);
  assert.equal(summary.groups[0].children[0].kind, 'addon');
  assert.equal(summary.groups[0].children[0].priceCents, 800);
  assert.equal(summary.groups[1].title, '肩颈调理');
  assert.equal(summary.groups[3].priceLabel, '赠饮');
});

test('会员已选清单保留门店价对比值，非会员不展示会员专属划线价', () => {
  const memberSummary = buildSelectionSummary({ projects: [footBath, local], addons: [addon], draft: draft(), isMember: true });
  assert.equal(memberSummary.groups[0].originalPriceCents, 3990);
  assert.equal(memberSummary.groups[0].children[0].originalPriceCents, 1200);
  assert.equal(memberSummary.groups[1].originalPriceCents, 6900);

  const storeSummary = buildSelectionSummary({ projects: [footBath, local], addons: [addon], draft: draft(), isMember: false });
  assert.equal(storeSummary.groups[0].originalPriceCents, null);
  assert.equal(storeSummary.groups[0].children[0].originalPriceCents, null);
});

test('免费加项在清单显示免费而不是零元价格', () => {
  const freeAddon = { ...addon, id: 12, name: '热毛巾', chargeable: false, prices: { store: 0, member: 0 } };
  const summary = buildSelectionSummary({
    projects: [footBath, local],
    addons: [freeAddon],
    draft: draft({ projectAddonIds: { 1: [12] }, localParts: [], tea: null }),
    isMember: false,
  });

  assert.equal(summary.groups[0].children[0].priceLabel, '免费');
});

test('未达成条件不展示减免，达成后只展示当前价格带的实际减免', () => {
  const base: PricingPreview = {
    storeSubtotalCents: 17790,
    memberSubtotalCents: 12790,
    storeAdjustmentCents: -3990,
    memberAdjustmentCents: -2990,
    storeTotalCents: 13800,
    memberTotalCents: 9800,
    qualified: false,
  };

  assert.equal(activePromotion(base, false), null);
  assert.deepEqual(activePromotion({ ...base, qualified: true }, false), {
    label: '泡脚组合减免',
    amountCents: -3990,
  });
  assert.equal(activePromotion({ ...base, qualified: true }, true)?.amountCents, -2990);
});

test('删除主项目同时清理它的偏好和加项但保留独立局部调理与赠饮', () => {
  const next = removeSelectionEntry(draft(), { kind: 'project', projectId: 1 });

  assert.deepEqual(next.selectedProjectIds, []);
  assert.deepEqual(next.projectPreferences, {});
  assert.deepEqual(next.projectAddonIds, {});
  assert.deepEqual(next.localParts, ['肩颈', '腿部']);
  assert.equal(next.tea, '老姜茶');
  assert.equal(countSelectionDraft(next), 3);
});

test('删除加项、单个局部和赠饮时不会影响其他选择', () => {
  const withoutAddon = removeSelectionEntry(draft(), { kind: 'addon', projectId: 1, addonId: 11 });
  const withoutLocal = removeSelectionEntry(withoutAddon, { kind: 'local', part: '肩颈' });
  const withoutTea = removeSelectionEntry(withoutLocal, { kind: 'tea' });

  assert.deepEqual(withoutAddon.selectedProjectIds, [1]);
  assert.deepEqual(withoutAddon.projectAddonIds, {});
  assert.deepEqual(withoutLocal.localParts, ['腿部']);
  assert.equal(withoutTea.tea, null);
  assert.equal(countSelectionDraft(withoutTea), 2);
});

test('重复的服务选择会合并为数量并按数量计算清单金额', () => {
  const repeated = draft({
    selectedProjectIds: [1, 1],
    localParts: ['肩颈', '肩颈', '腿部'],
  });
  const summary = buildSelectionSummary({
    projects: [footBath, local],
    addons: [addon],
    draft: repeated,
    isMember: true,
  });

  assert.equal(summary.groups[0].quantity, 2);
  assert.equal(summary.groups[0].priceCents, 5980);
  assert.equal(summary.groups[0].children[0].quantity, 2);
  assert.equal(summary.groups[0].children[0].priceCents, 1600);
  assert.equal(summary.groups[1].title, '肩颈调理');
  assert.equal(summary.groups[1].quantity, 2);
  assert.equal(summary.groups[1].priceCents, 9800);
  assert.equal(summary.totalCount, 8);
});

test('提交项目和前端预计金额沿用清单中的数量', () => {
  const input = {
    projects: [footBath, local],
    addons: [addon],
    selectedProjectIds: [1, 1],
    projectAddonIds: { 1: [11] },
    projectPreferences: { 1: ['适中'] },
    localParts: ['肩颈', '肩颈', '腿部'],
    tea: '老姜茶',
  };

  const items = buildSelectionItems(input);
  assert.deepEqual(items.map((item) => [item.project_id, item.quantity]), [
    [1, 2],
    [2, 2],
    [2, 1],
    ['tea', 1],
  ]);

  const preview = calculatePreviewPricing(input);
  assert.equal(preview.storeSubtotalCents, 31080);
  assert.equal(preview.memberSubtotalCents, 22280);
  assert.equal(preview.storeAdjustmentCents, -3990);
  assert.equal(preview.memberAdjustmentCents, -2990);
  assert.equal(preview.storeTotalCents, 27090);
  assert.equal(preview.memberTotalCents, 19290);
});

test('加减控件每次只调整一个服务单位，减到零时清理项目配置', () => {
  const changeSelectionQuantity = (
    selectionSummaryModule as typeof selectionSummaryModule & {
      changeSelectionQuantity?: (
        current: SelectionDraft,
        target: { kind: 'project'; projectId: number } | { kind: 'local'; part: string },
        delta: 1 | -1,
      ) => SelectionDraft;
    }
  ).changeSelectionQuantity;
  assert.equal(typeof changeSelectionQuantity, 'function');
  if (!changeSelectionQuantity) return;

  const increased = changeSelectionQuantity(draft(), { kind: 'project', projectId: 1 }, 1);
  assert.deepEqual(increased.selectedProjectIds, [1, 1]);
  const decreased = changeSelectionQuantity(increased, { kind: 'project', projectId: 1 }, -1);
  assert.deepEqual(decreased.selectedProjectIds, [1]);
  const removed = changeSelectionQuantity(decreased, { kind: 'project', projectId: 1 }, -1);
  assert.deepEqual(removed.selectedProjectIds, []);
  assert.deepEqual(removed.projectPreferences, {});
  assert.deepEqual(removed.projectAddonIds, {});

  const localIncreased = changeSelectionQuantity(draft(), { kind: 'local', part: '肩颈' }, 1);
  assert.deepEqual(localIncreased.localParts, ['肩颈', '腿部', '肩颈']);
  const localDecreased = changeSelectionQuantity(localIncreased, { kind: 'local', part: '肩颈' }, -1);
  assert.deepEqual(localDecreased.localParts, ['肩颈', '腿部']);
});

import assert from 'node:assert/strict';
import test from 'node:test';

import {
  MENU_SYNC_INTERVAL_MS,
  isProjectInMenu,
  loadMenuSyncUpdate,
  menuFingerprint,
  menuUpdateNotice,
  reconcileDraftToMenu,
  shouldApplyMenuSyncResponse,
  type MenuDraft,
} from '../src/menuSync.ts';
import type { CatalogOptionGroup } from '../src/catalogOptions.ts';
import type { Addon, Project } from '../src/domain.ts';

function project(id: number, overrides: Partial<Project> = {}): Project {
  return {
    id,
    code: `code-${id}`,
    category: 'bath',
    category_mark: '泡',
    name: `项目${id}`,
    duration_min: 30,
    summary: '',
    image_url: '',
    tags: [],
    price_label: '',
    prices: [{ price_type: 'store', amount_cents: 9900 }, { price_type: 'member', amount_cents: 7900 }],
    ...overrides,
  };
}

function addon(id: number, overrides: Partial<Addon> = {}): Addon {
  return {
    id,
    code: `addon-${id}`,
    name: `加项${id}`,
    parent_project_id: null,
    duration_min: 15,
    summary: '',
    image_url: '',
    display_order: 0,
    chargeable: true,
    independently_sellable: false,
    can_attach_to_parent: true,
    prices: { store: 3900, member: 2900 },
    ...overrides,
  };
}

function optionGroups(status: 'active' | 'inactive' = 'active'): CatalogOptionGroup[] {
  return [{
    id: 5,
    code: 'pressure',
    name: '力度',
    description: '',
    selection_mode: 'single',
    required: true,
    min_select: 1,
    max_select: 1,
    display_order: 0,
    choices: [{
      id: 7,
      code: 'pressure-medium',
      name: '适中',
      description: '',
      choice_type: 'preference',
      linked_project_id: null,
      linked_project_code: null,
      linked_catalog_version_id: null,
      charge_mode: 'free',
      independently_visible: true,
      coupon_eligible: false,
      annual_gift_eligible: false,
      qualifies_for_foot_bath_bundle: false,
      display_order: 0,
      status,
      prices: [],
    }],
  }];
}

function draft(overrides: Partial<MenuDraft> = {}): MenuDraft {
  return {
    selectedProjectIds: [1, 2],
    projectPreferences: { 1: ['适中'], 2: [] },
    projectAddonIds: { 1: [11, 12] },
    projectCatalogSelections: { 1: { projectId: 1, catalogVersionId: 3, optionChoiceIds: [7] } },
    ...overrides,
  };
}

test('价格、项目上下架、选项状态和加项价格都会改变菜单指纹', () => {
  const baseProject = project(1, { catalog_version_id: 3, option_groups: optionGroups() });
  const before = menuFingerprint([baseProject], [addon(11)]);

  assert.notEqual(before, menuFingerprint([project(1, { catalog_version_id: 3, option_groups: optionGroups(), prices: [{ price_type: 'store', amount_cents: 10900 }] })], [addon(11)]));
  assert.notEqual(before, menuFingerprint([], [addon(11)]));
  assert.notEqual(before, menuFingerprint([project(1, { catalog_version_id: 3, option_groups: optionGroups('inactive') })], [addon(11)]));
  assert.notEqual(before, menuFingerprint([baseProject], [addon(11, { prices: { store: 4900, member: 2900 } })]));
});

test('图片与详情内容变化不会触发价格菜单刷新', () => {
  const before = menuFingerprint([project(1)], [addon(11)]);
  const after = menuFingerprint(
    [project(1, { image_url: '/assets/new.webp', detail_modules: [{ type: 'text', title: '新增说明' }] })],
    [addon(11, { image_url: '/assets/new-addon.webp' })],
  );
  assert.equal(before, after);
});

test('项目下架时移除项目及其偏好、加项和目录选择', () => {
  const result = reconcileDraftToMenu(draft(), [project(1, { catalog_version_id: 3, option_groups: optionGroups() })], [addon(11)]);

  assert.deepEqual(result.removedProjectIds, [2]);
  assert.deepEqual(result.draft.selectedProjectIds, [1]);
  assert.equal(2 in result.draft.projectPreferences, false);
  assert.equal(2 in result.draft.projectAddonIds, false);
  assert.equal(2 in (result.draft.projectCatalogSelections || {}), false);
});

test('加项下架或不再允许关联时只清理失效加项', () => {
  const result = reconcileDraftToMenu(
    draft({ selectedProjectIds: [1] }),
    [project(1, { catalog_version_id: 3, option_groups: optionGroups() })],
    [addon(11), addon(12, { can_attach_to_parent: false })],
  );

  assert.deepEqual(result.draft.selectedProjectIds, [1]);
  assert.deepEqual(result.draft.projectAddonIds, { 1: [11] });
  assert.deepEqual(result.removedAddonIds, [12]);
});

test('必选目录选项失效或目录版本变化时移除该项目，要求顾客重新选择', () => {
  const inactive = reconcileDraftToMenu(
    draft({ selectedProjectIds: [1] }),
    [project(1, { catalog_version_id: 3, option_groups: optionGroups('inactive') })],
    [addon(11)],
  );
  const newVersion = reconcileDraftToMenu(
    draft({ selectedProjectIds: [1] }),
    [project(1, { catalog_version_id: 4, option_groups: optionGroups() })],
    [addon(11)],
  );

  assert.deepEqual(inactive.draft.selectedProjectIds, []);
  assert.deepEqual(inactive.reselectionProjectIds, [1]);
  assert.deepEqual(newVersion.draft.selectedProjectIds, []);
  assert.deepEqual(newVersion.reselectionProjectIds, [1]);
});

test('目录刷新后必选组为空时不得保留可直接提交的无效项目', () => {
  const result = reconcileDraftToMenu(
    draft({
      selectedProjectIds: [1],
      projectCatalogSelections: { 1: { projectId: 1, catalogVersionId: 3, optionChoiceIds: [] } },
    }),
    [project(1, { catalog_version_id: 3, option_groups: optionGroups() })],
    [addon(11)],
  );

  assert.deepEqual(result.draft.selectedProjectIds, []);
  assert.deepEqual(result.reselectionProjectIds, [1]);
});

test('仍在售且目录版本与选项有效时保留草稿', () => {
  const current = draft({ selectedProjectIds: [1], projectAddonIds: { 1: [11] } });
  const result = reconcileDraftToMenu(
    current,
    [project(1, { catalog_version_id: 3, option_groups: optionGroups() })],
    [addon(11)],
  );

  assert.deepEqual(result.draft, current);
  assert.equal(result.changed, false);
});

test('过时、跨店或保存提交中的异步响应不得落地', () => {
  assert.equal(shouldApplyMenuSyncResponse({ requestStoreId: 1, currentStoreId: 1, requestId: 3, latestRequestId: 3, saving: false, submitting: false }), true);
  assert.equal(shouldApplyMenuSyncResponse({ requestStoreId: 1, currentStoreId: 2, requestId: 3, latestRequestId: 3, saving: false, submitting: false }), false);
  assert.equal(shouldApplyMenuSyncResponse({ requestStoreId: 1, currentStoreId: 1, requestId: 2, latestRequestId: 3, saving: false, submitting: false }), false);
  assert.equal(shouldApplyMenuSyncResponse({ requestStoreId: 1, currentStoreId: 1, requestId: 3, latestRequestId: 3, saving: true, submitting: false }), false);
  assert.equal(shouldApplyMenuSyncResponse({ requestStoreId: 1, currentStoreId: 1, requestId: 3, latestRequestId: 3, saving: false, submitting: true }), false);
});

test('价格或选项更新与失效草稿分别给出说人话提示', () => {
  assert.equal(menuUpdateNotice({ removedProjectIds: [], removedAddonIds: [], reselectionProjectIds: [] }), '门店菜单已更新，价格和可选项已同步');
  assert.equal(menuUpdateNotice({ removedProjectIds: [2], removedAddonIds: [], reselectionProjectIds: [] }), '门店菜单已更新，1 个下架项目已从本次选择中移除');
  assert.equal(menuUpdateNotice({ removedProjectIds: [], removedAddonIds: [12], reselectionProjectIds: [] }), '门店菜单已更新，1 个失效加项已从本次选择中移除');
  assert.equal(menuUpdateNotice({ removedProjectIds: [], removedAddonIds: [], reselectionProjectIds: [1] }), '门店菜单已更新，请重新选择 1 个项目');
});

test('项目存续判断和同步间隔保持稳定', () => {
  assert.equal(isProjectInMenu([project(1)], 1), true);
  assert.equal(isProjectInMenu([project(1)], 2), false);
  assert.equal(isProjectInMenu([project(1)], null), false);
  assert.equal(MENU_SYNC_INTERVAL_MS, 60_000);
});

test('页面菜单刷新等待真实项目和加项响应后再原子生成更新', async () => {
  const beforeProjects = [project(1, { prices: [{ price_type: 'store', amount_cents: 9900 }] })];
  const beforeAddons = [addon(11)];
  const nextProjects = [project(1, { prices: [{ price_type: 'store', amount_cents: 10900 }] })];
  const nextAddons = [addon(11, { prices: { store: 4900, member: 2900 } })];

  const result = await loadMenuSyncUpdate({
    requestStoreId: 1,
    requestId: 4,
    loadProjects: async () => nextProjects,
    loadAddons: async () => nextAddons,
    readContext: () => ({
      currentStoreId: 1,
      latestRequestId: 4,
      saving: false,
      submitting: false,
      previousFingerprint: menuFingerprint(beforeProjects, beforeAddons),
      draft: draft({
        selectedProjectIds: [1],
        projectAddonIds: { 1: [11] },
        projectCatalogSelections: {},
      }),
      detailProjectId: 1,
    }),
  });

  assert.ok(result);
  assert.deepEqual(result.projects, nextProjects);
  assert.deepEqual(result.addons, nextAddons);
  assert.equal(result.notice, '门店菜单已更新，价格和可选项已同步');
  assert.equal(result.detailProject?.prices[0]?.amount_cents, 10900);
});

test('页面菜单刷新在响应返回前切店或开始保存提交时不落地旧响应', async () => {
  let currentStoreId = 1;
  let saving = false;
  let submitting = false;
  let releaseProjects!: (projects: Project[]) => void;
  const pendingProjects = new Promise<Project[]>((resolve) => { releaseProjects = resolve; });
  const request = loadMenuSyncUpdate({
    requestStoreId: 1,
    requestId: 8,
    loadProjects: async () => pendingProjects,
    loadAddons: async () => [addon(11)],
    readContext: () => ({
      currentStoreId,
      latestRequestId: 8,
      saving,
      submitting,
      previousFingerprint: '',
      draft: draft({ selectedProjectIds: [1] }),
      detailProjectId: 1,
    }),
  });
  currentStoreId = 2;
  saving = true;
  submitting = true;
  releaseProjects([project(1)]);

  assert.equal(await request, null);
});

test('页面菜单刷新遇到失效必选项时返回可直接应用的清理结果与提示', async () => {
  const result = await loadMenuSyncUpdate({
    requestStoreId: 1,
    requestId: 2,
    loadProjects: async () => [project(1, { catalog_version_id: 3, option_groups: optionGroups('inactive') })],
    loadAddons: async () => [addon(11)],
    readContext: () => ({
      currentStoreId: 1,
      latestRequestId: 2,
      saving: false,
      submitting: false,
      previousFingerprint: '',
      draft: draft({ selectedProjectIds: [1] }),
      detailProjectId: 1,
    }),
  });

  assert.ok(result);
  assert.deepEqual(result.reconciliation.draft.selectedProjectIds, []);
  assert.deepEqual(result.reconciliation.reselectionProjectIds, [1]);
  assert.equal(result.notice, '门店菜单已更新，请重新选择 1 个项目');
});

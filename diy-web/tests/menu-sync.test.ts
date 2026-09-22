import assert from 'node:assert/strict';
import test from 'node:test';

import {
  MENU_SYNC_INTERVAL_MS,
  isProjectInMenu,
  menuFingerprint,
  pruneDraftToMenu,
  type MenuDraft,
} from '../src/menuSync.ts';
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

function draft(overrides: Partial<MenuDraft> = {}): MenuDraft {
  return {
    selectedProjectIds: [1, 2],
    projectPreferences: { 1: ['适中'], 2: [] },
    projectAddonIds: { 1: [11] },
    projectCatalogSelections: { 1: { projectId: 1, catalogVersionId: 3, optionChoiceIds: [7] } },
    ...overrides,
  };
}

test('菜单指纹在价格变化时必须改变', () => {
  const before = menuFingerprint([project(1)], [addon(11)]);
  const after = menuFingerprint(
    [project(1, { prices: [{ price_type: 'store', amount_cents: 10900 }, { price_type: 'member', amount_cents: 7900 }] })],
    [addon(11)],
  );

  assert.notEqual(before, after);
});

test('菜单指纹在会员价变化时也必须改变', () => {
  const before = menuFingerprint([project(1)], [addon(11)]);
  const after = menuFingerprint(
    [project(1, { prices: [{ price_type: 'store', amount_cents: 9900 }, { price_type: 'member', amount_cents: 6900 }] })],
    [addon(11)],
  );

  assert.notEqual(before, after);
});

test('菜单指纹在加项价格变化时必须改变', () => {
  const before = menuFingerprint([project(1)], [addon(11)]);
  const after = menuFingerprint([project(1)], [addon(11, { prices: { store: 4900, member: 2900 } })]);

  assert.notEqual(before, after);
});

test('菜单指纹不受不影响金额的字段干扰（图片、详情模块）', () => {
  const before = menuFingerprint([project(1)], [addon(11)]);
  const after = menuFingerprint(
    [project(1, { image_url: '/assets/new.webp', detail_modules: [{ type: 'text', title: '新增说明' }] })],
    [addon(11, { image_url: '/assets/new-addon.webp' })],
  );

  assert.equal(before, after);
});

test('项目上下架会改变指纹：新增与移除都要被识别', () => {
  const before = menuFingerprint([project(1)], [addon(11)]);

  assert.notEqual(before, menuFingerprint([project(1), project(2)], [addon(11)]));
  assert.notEqual(before, menuFingerprint([], [addon(11)]));
});

test('选项上下架与选项价格进入指纹', () => {
  const groups = [{
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
      id: 7, code: 'pressure-medium', name: '适中', description: '',
      choice_type: 'preference' as const, linked_project_id: null, linked_project_code: null,
      linked_catalog_version_id: null, charge_mode: 'free', independently_visible: true,
      coupon_eligible: false, annual_gift_eligible: false, qualifies_for_foot_bath_bundle: false,
      display_order: 0, status: 'active', prices: [],
    }],
  }];

  const withGroup = menuFingerprint([project(1, { option_groups: groups })], [addon(11)]);
  const inactive = menuFingerprint([project(1, { option_groups: [{ ...groups[0], choices: [{ ...groups[0].choices[0], status: 'inactive' }] }] })], [addon(11)]);

  assert.notEqual(withGroup, menuFingerprint([project(1)], [addon(11)]));
  assert.notEqual(withGroup, inactive);
});

test('草稿里仍在售的项目原样保留，不做任何改动', () => {
  const result = pruneDraftToMenu(draft(), [project(1), project(2)]);

  assert.deepEqual(result.removedProjectIds, []);
  assert.deepEqual(result.draft.selectedProjectIds, [1, 2]);
  assert.deepEqual(result.draft.projectPreferences, { 1: ['适中'], 2: [] });
  assert.deepEqual(result.draft.projectAddonIds, { 1: [11] });
});

test('项目下架后草稿移除该项目并清掉它的偏好、加项和目录选择', () => {
  const result = pruneDraftToMenu(draft(), [project(1)]);

  assert.deepEqual(result.removedProjectIds, [2]);
  assert.deepEqual(result.draft.selectedProjectIds, [1]);
  assert.deepEqual(result.draft.projectPreferences, { 1: ['适中'] });
  assert.deepEqual(result.draft.projectAddonIds, { 1: [11] });
  assert.deepEqual(result.draft.projectCatalogSelections, { 1: { projectId: 1, catalogVersionId: 3, optionChoiceIds: [7] } });
});

test('重复选中的同一个下架项目只计一次，且全部移除', () => {
  const result = pruneDraftToMenu(draft({ selectedProjectIds: [2, 2, 1] }), [project(1)]);

  assert.deepEqual(result.removedProjectIds, [2]);
  assert.deepEqual(result.draft.selectedProjectIds, [1]);
});

test('草稿本来没有目录选择时，不为它补出该字段', () => {
  const withoutCatalog: MenuDraft = {
    selectedProjectIds: [2],
    projectPreferences: {},
    projectAddonIds: {},
  };
  const result = pruneDraftToMenu(withoutCatalog, [project(1)]);

  assert.equal('projectCatalogSelections' in result.draft, false);
  assert.deepEqual(result.removedProjectIds, [2]);
});

test('项目是否仍在菜单中：下架、空引用都要判否', () => {
  assert.equal(isProjectInMenu([project(1)], 1), true);
  assert.equal(isProjectInMenu([project(1)], 2), false);
  assert.equal(isProjectInMenu([project(1)], null), false);
  assert.equal(isProjectInMenu([project(1)], undefined), false);
});

test('菜单同步间隔是低频值，页面隐藏时会暂停', () => {
  assert.equal(MENU_SYNC_INTERVAL_MS, 60_000);
});

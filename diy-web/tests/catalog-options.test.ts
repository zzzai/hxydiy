import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
  applyProjectCatalogSelection,
  catalogDraftResetKey,
  catalogChoicePriceCents,
  linkedProjectSelections,
  withRequiredCatalogDefaults,
  validateCatalogSelection,
  type CatalogOptionChoice,
  type CatalogOptionGroup,
  type ProjectCatalogSelection,
} from '../src/catalogOptions.ts';
import { buildSelectionItems, type Project } from '../src/domain.ts';
import type { SelectionDraft } from '../src/selectionSummary.ts';
import { bundleProgressCount, catalogChoicesByType, linkedProjectIdsForChoices, removeSelectionEntry } from '../src/selectionSummary.ts';

function project(partial: Partial<Project> & Pick<Project, 'id' | 'code' | 'category' | 'name'>): Project {
  return {
    category_mark: '泡', duration_min: 30, summary: '', image_url: '', tags: [], price_label: '', prices: [
      { price_type: 'store', amount_cents: 3990 },
      { price_type: 'member', amount_cents: 2990 },
    ],
    ...partial,
  };
}

const qiqing = project({ id: 1, code: 'hxy-qiqing-30', category: 'bath', name: '39.9 泡脚' });
const xiaoqi = project({ id: 2, code: 'hxy-xiaoqi-90', category: 'bath', name: '90 分钟沐足' });
const cupping = project({ id: 101, code: 'hxy-baguan-20', category: 'small', name: '拔罐' });
const local = project({ id: 102, code: 'hxy-jubu-30', category: 'local-strength', name: '局部调理' });

const cuppingFromQiqing = 1001;
const cuppingFromXiaoqi = 2001;
const localShoulder = 1002;
const localLeg = 1003;

test('目录选择类型只接受协议规定的三种值', () => {
  const supported: CatalogOptionChoice['choice_type'][] = ['preference', 'linked_project', 'dedicated_charge'];
  assert.deepEqual(supported, ['preference', 'linked_project', 'dedicated_charge']);

  if (false) {
    // @ts-expect-error 目录协议不允许第四种收费或选择类型。
    const unsupported: CatalogOptionChoice['choice_type'] = 'online_payment';
    void unsupported;
  }
});

const optionGroups: CatalogOptionGroup[] = [
  {
    id: 11, code: 'small-services', name: '小项', description: '', selection_mode: 'multiple', required: true,
    min_select: 1, max_select: 2, display_order: 10,
    choices: [
      {
        id: cuppingFromQiqing, code: 'cupping-a', name: '拔罐', description: '', choice_type: 'linked_project',
        linked_project_id: 101, linked_project_code: 'hxy-baguan-20', linked_catalog_version_id: null,
        charge_mode: 'inherit_linked_price', independently_visible: true, coupon_eligible: true,
        annual_gift_eligible: true, qualifies_for_foot_bath_bundle: false, display_order: 1, status: 'active', prices: [],
      },
      {
        id: cuppingFromXiaoqi, code: 'cupping-b', name: '拔罐', description: '', choice_type: 'linked_project',
        linked_project_id: 101, linked_project_code: 'hxy-baguan-20', linked_catalog_version_id: null,
        charge_mode: 'inherit_linked_price', independently_visible: true, coupon_eligible: true,
        annual_gift_eligible: true, qualifies_for_foot_bath_bundle: false, display_order: 2, status: 'active', prices: [],
      },
    ],
  },
  {
    id: 12, code: 'local-strength', name: '局部加强', description: '', selection_mode: 'multiple', required: false,
    min_select: 0, max_select: 2, display_order: 20,
    choices: [
      {
        id: localShoulder, code: 'local-shoulder', name: '肩颈', description: '', choice_type: 'linked_project',
        linked_project_id: 102, linked_project_code: 'hxy-jubu-30', linked_catalog_version_id: null,
        charge_mode: 'inherit_linked_price', independently_visible: true, coupon_eligible: true,
        annual_gift_eligible: true, qualifies_for_foot_bath_bundle: true, display_order: 1, status: 'active', prices: [], body_part: ' 肩颈 ',
      },
      {
        id: localLeg, code: 'local-leg', name: '腿部', description: '', choice_type: 'linked_project',
        linked_project_id: 102, linked_project_code: 'hxy-jubu-30', linked_catalog_version_id: null,
        charge_mode: 'inherit_linked_price', independently_visible: true, coupon_eligible: true,
        annual_gift_eligible: true, qualifies_for_foot_bath_bundle: true, display_order: 2, status: 'active', prices: [], body_part: '腿部',
      },
    ],
  },
];

test('同一正式小项从两个主项目引用时只生成一个初始服务单位', () => {
  const linked = linkedProjectSelections([qiqing, xiaoqi, cupping, local], optionGroups, [cuppingFromQiqing, cuppingFromXiaoqi]);

  assert.deepEqual(linked.map((item) => item.projectId), [101]);
  assert.equal(linked[0].quantity, 1);
  assert.deepEqual(linked[0].optionChoiceIds, [1001, 2001]);
});

test('局部项目按规范化部位去重而不同部位保留为独立服务单位', () => {
  const repeatedShoulder = { ...optionGroups[1].choices[0], id: 1004, body_part: '肩颈' };
  const groups = [{ ...optionGroups[1], choices: [...optionGroups[1].choices, repeatedShoulder] }];
  const linked = linkedProjectSelections([qiqing, xiaoqi, cupping, local], groups, [localShoulder, localLeg, 1004]);

  assert.deepEqual(linked.map((item) => [item.projectId, item.bodyPart, item.quantity]), [
    [102, '肩颈', 1],
    [102, '腿部', 1],
  ]);
});

test('目录未显式返回部位时从局部选择项名称识别服务部位', () => {
  const withoutBodyPart = {
    ...optionGroups[1].choices[0],
    body_part: undefined,
    bodyPart: undefined,
    name: '肩颈',
  };
  const groups = [{ ...optionGroups[1], choices: [withoutBodyPart] }];

  const linked = linkedProjectSelections([local], groups, [withoutBodyPart.id]);

  assert.deepEqual(linked, [{
    projectId: local.id,
    quantity: 1,
    optionChoiceIds: [withoutBodyPart.id],
    bodyPart: '肩颈',
  }]);
});

test('校验拒绝重复、未知选择，以及未满足必选组的选择', () => {
  const duplicate = validateCatalogSelection(optionGroups, [cuppingFromQiqing, cuppingFromQiqing]);
  const unknown = validateCatalogSelection(optionGroups, [9999]);
  const missingRequired = validateCatalogSelection(optionGroups, []);

  assert.deepEqual(duplicate.map((error) => error.code), ['OPTION_CHOICE_DUPLICATE']);
  assert.deepEqual(unknown.map((error) => error.code), ['OPTION_CHOICE_UNKNOWN', 'OPTION_GROUP_REQUIRED']);
  assert.deepEqual(missingRequired.map((error) => error.code), ['OPTION_GROUP_REQUIRED']);
});

test('目录选择写入服务 payload，保留且仅保留版本和选项 ID', () => {
  const selection: ProjectCatalogSelection = {
    projectId: 1, catalogVersionId: 901, optionChoiceIds: [1001, 1002],
  };
  const items = buildSelectionItems({
    projects: [qiqing], selectedProjectIds: [1], localParts: [], tea: null,
    projectCatalogSelections: { 1: selection },
  });

  assert.deepEqual(items, [{
    project_id: 1, quantity: 1, addon_ids: [], diy_preferences: [], item_type: 'service', chargeable: true,
    catalog_version_id: 901, option_choice_ids: [1001, 1002],
  }]);
});

test('保存同一主项目目录选择时覆盖旧 ID 并保留其他草稿字段', () => {
  const draft = {
    selectedProjectIds: [1], projectPreferences: { 1: ['适中'] }, projectAddonIds: { 1: [6] }, localParts: ['肩颈'], tea: '老姜茶',
    projectCatalogSelections: { 1: { projectId: 1, catalogVersionId: 11, optionChoiceIds: [12] } },
  };
  const next = applyProjectCatalogSelection(draft, { projectId: 1, catalogVersionId: 901, optionChoiceIds: [1001, 1002] });

  assert.deepEqual(next.projectCatalogSelections, {
    1: { projectId: 1, catalogVersionId: 901, optionChoiceIds: [1001, 1002] },
  });
  assert.deepEqual(next.selectedProjectIds, [1]);
  assert.deepEqual(next.projectPreferences, { 1: ['适中'] });
  assert.deepEqual(next.localParts, ['肩颈']);
  assert.equal(next.tea, '老姜茶');
});

test('从草本沐足选择目录小项和局部后保存并恢复全局已选状态', () => {
  const emptyDraft: SelectionDraft = {
    selectedProjectIds: [], projectPreferences: {}, projectAddonIds: {},
    projectCatalogSelections: {}, localParts: [], tea: null,
  };
  const saved = applyProjectCatalogSelection(emptyDraft, {
    projectId: 2,
    catalogVersionId: 3,
    optionChoiceIds: [cuppingFromQiqing, localShoulder],
    linkedProjectIds: [101, 102],
    localParts: ['肩颈'],
  });
  assert.deepEqual(saved.selectedProjectIds, [2, 101, 102]);
  assert.deepEqual(saved.projectCatalogSelections?.[2]?.optionChoiceIds, [cuppingFromQiqing, localShoulder]);
  assert.deepEqual(saved.localParts, ['肩颈']);
});

test('删除主项目时仅清理主项目目录选择，不删除独立引用项目或局部部位', () => {
  const draft: SelectionDraft = {
    selectedProjectIds: [2, 101, 102], projectPreferences: {}, projectAddonIds: {},
    projectCatalogSelections: { 2: { projectId: 2, catalogVersionId: 3, optionChoiceIds: [cuppingFromQiqing, localShoulder] } },
    localParts: ['肩颈'], tea: null,
  };
  const next = removeSelectionEntry(draft, { kind: 'project', projectId: 2 });
  assert.deepEqual(next.selectedProjectIds, [101, 102]);
  assert.deepEqual(next.projectCatalogSelections, {});
  assert.deepEqual(next.localParts, ['肩颈']);
});

test('已发布目录按类型提供偏好与引用项目，并把实时预览引用项目去重', () => {
  const preference: CatalogOptionChoice = {
    id: 1000, code: 'pressure-medium', name: '适中', description: '门店推荐', choice_type: 'preference',
    linked_project_id: null, linked_project_code: null, linked_catalog_version_id: null,
    charge_mode: 'free', independently_visible: false, coupon_eligible: false,
    annual_gift_eligible: false, qualifies_for_foot_bath_bundle: false, display_order: 0,
    status: 'active', prices: [],
  };
  assert.deepEqual(catalogChoicesByType([...optionGroups, {
    ...optionGroups[0], id: 13, code: 'preference', choices: [preference],
  }], 'preference').map((choice) => choice.id), [1000]);
  assert.deepEqual(linkedProjectIdsForChoices(optionGroups, [cuppingFromQiqing, cuppingFromXiaoqi, localShoulder]), [101, 102]);
});

test('组合减免进度按不同局部部位计数，不因同一部位重复而显示达成', () => {
  assert.equal(bundleProgressCount({ qualified: false }, ['肩颈', '肩颈']), 1);
  assert.equal(bundleProgressCount({ qualified: false }, ['肩颈', '腰臀']), 2);
});

test('目录详情页默认泡脚液、适中力度和首个 SPA 精油且保留顾客已选值', () => {
  const requiredGroups: CatalogOptionGroup[] = [
    {
      id: 21, code: 'footbath-liquid', name: '泡脚液', description: '', selection_mode: 'single', required: true,
      min_select: 1, max_select: 1, display_order: 10,
      choices: [
        { ...optionGroups[0].choices[0], id: 2101, code: 'ginger', name: '老姜', choice_type: 'preference', linked_project_id: null, linked_project_code: null, charge_mode: 'free', display_order: 0 },
        { ...optionGroups[0].choices[0], id: 2102, code: 'mugwort', name: '艾草', choice_type: 'preference', linked_project_id: null, linked_project_code: null, charge_mode: 'free', display_order: 1 },
      ],
    },
    {
      id: 22, code: 'pressure', name: '力度', description: '', selection_mode: 'single', required: true,
      min_select: 1, max_select: 1, display_order: 20,
      choices: [
        { ...optionGroups[0].choices[0], id: 2200, code: 'pressure-light', name: '轻柔', choice_type: 'preference', linked_project_id: null, linked_project_code: null, charge_mode: 'free', display_order: 0 },
        { ...optionGroups[0].choices[0], id: 2201, code: 'pressure-medium', name: '适中', choice_type: 'preference', linked_project_id: null, linked_project_code: null, charge_mode: 'free', display_order: 1 },
        { ...optionGroups[0].choices[0], id: 2202, code: 'pressure-strong', name: '强力', choice_type: 'preference', linked_project_id: null, linked_project_code: null, charge_mode: 'free', display_order: 2 },
      ],
    },
    {
      id: 23, code: 'spa-oil', name: '精油', description: '', selection_mode: 'single', required: true,
      min_select: 1, max_select: 1, display_order: 30,
      choices: [
        { ...optionGroups[0].choices[0], id: 2301, code: 'spa-oil-lavender', name: '薰衣草精油', choice_type: 'preference', linked_project_id: null, linked_project_code: null, charge_mode: 'free', display_order: 0 },
        { ...optionGroups[0].choices[0], id: 2302, code: 'spa-oil-rose', name: '玫瑰精油', choice_type: 'preference', linked_project_id: null, linked_project_code: null, charge_mode: 'free', display_order: 1 },
      ],
    },
  ];

  assert.deepEqual(withRequiredCatalogDefaults(requiredGroups, []), [2101, 2201, 2301]);
  assert.deepEqual(withRequiredCatalogDefaults(requiredGroups, [2102, 2202, 2302]), [2102, 2202, 2302]);
  assert.deepEqual(validateCatalogSelection(requiredGroups, withRequiredCatalogDefaults(requiredGroups, [])).map((error) => error.code), []);
});

test('收费目录卡片按当前身份显示被引用正式项目价格', () => {
  const choice = optionGroups[0].choices[0];
  const pricedProject = project({
    ...cupping,
    prices: [
      { price_type: 'store', amount_cents: 5900 },
      { price_type: 'group', amount_cents: 4900 },
      { price_type: 'member', amount_cents: 3900 },
    ],
  });

  assert.equal(catalogChoicePriceCents(choice, [pricedProject], false), 5900);
  assert.equal(catalogChoicePriceCents(choice, [pricedProject], true), 3900);
  assert.equal(catalogChoicePriceCents({ ...choice, charge_mode: 'free' }, [pricedProject], false), 0);
});

test('父页面用等值新数组重渲染时不重置详情页内尚未确认的选择', () => {
  const first = catalogDraftResetKey({
    projectId: 2,
    preferences: [],
    selectedAddonIds: [],
    localParts: [],
    catalogVersionId: 3,
    optionChoiceIds: [2101, 2201],
  });
  const equivalentRerender = catalogDraftResetKey({
    projectId: 2,
    preferences: [...[]],
    selectedAddonIds: [...[]],
    localParts: [...[]],
    catalogVersionId: 3,
    optionChoiceIds: [...[2101, 2201]],
  });
  const changedSavedSelection = catalogDraftResetKey({
    projectId: 2,
    preferences: [],
    selectedAddonIds: [],
    localParts: [],
    catalogVersionId: 3,
    optionChoiceIds: [2102, 2201],
  });

  assert.equal(equivalentRerender, first);
  assert.notEqual(changedSavedSelection, first);
});

test('泡脚减免提示为文案和状态两列，移动端文案不会被压进图标占位列', () => {
  const styles = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');
  const rule = styles.match(/\.mini-promotion\s*\{([^}]*)\}/)?.[1] || '';

  assert.match(rule, /grid-template-columns:\s*minmax\(0,\s*1fr\)\s+auto/);
  assert.doesNotMatch(rule, /grid-template-columns:\s*20px\s+1fr\s+auto/);
});

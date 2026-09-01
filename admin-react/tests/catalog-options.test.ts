import assert from 'node:assert/strict';
import test from 'node:test';

import {
  catalogPublishState,
  catalogValidationMessage,
  formatCents,
  optionChoicePayload,
  optionChoiceFormValues,
  optionGroupPayload,
  nextTuesdayIso,
  previewChoiceIds,
  type OptionChoiceForm,
} from '../src/catalogOptions.ts';

test('项目引用选项固定继承正式项目价格', () => {
  const payload = optionChoicePayload({
    code: 'cupping', name: '拔罐', choice_type: 'linked_project', linked_project_id: 8,
  });
  assert.equal(payload.charge_mode, 'inherit_linked_price');
  assert.deepEqual(payload.prices, []);
});

test('免费偏好不生成收费价格', () => {
  const payload = optionChoicePayload({
    code: 'pressure', name: '适中', choice_type: 'preference', charge_mode: 'free',
  });
  assert.equal(payload.charge_mode, 'free');
  assert.deepEqual(payload.prices, []);
  assert.equal(payload.linked_project_id, null);
});

test('专属收费选项保留三档价格', () => {
  const payload = optionChoicePayload({
    code: 'oil', name: '草本精油', choice_type: 'dedicated_charge', charge_mode: 'custom_price',
    prices: [{ price_type: 'store', amount_cents: 3000 }, { price_type: 'group', amount_cents: 2800 }, { price_type: 'member', amount_cents: 2500 }],
  });
  assert.deepEqual(payload.prices, [
    { price_type: 'store', amount_cents: 3000 },
    { price_type: 'group', amount_cents: 2800 },
    { price_type: 'member', amount_cents: 2500 },
  ]);
});

test('选项组 payload 规范化数量约束', () => {
  const payload = optionGroupPayload({ code: 'small', name: '小项', selection_mode: 'multiple', required: true, min_select: 1, max_select: 2, display_order: 4 });
  assert.deepEqual(payload, { code: 'small', name: '小项', description: '', selection_mode: 'multiple', required: true, min_select: 1, max_select: 2, display_order: 4 });
});

test('存在发布错误时禁用发布按钮并显示中文路径', () => {
  const state = catalogPublishState([{ code: 'linked_project_unpublished', path: 'groups.small.choices.cupping' }]);
  assert.equal(state.canPublish, false);
  assert.match(state.messages[0], /拔罐|引用项目|未发布/);
});

test('发布错误代码和路径都能转成可读文案', () => {
  assert.match(catalogValidationMessage({ code: 'option_group_required', path: 'groups.small' }), /选项组|必选/);
  assert.match(catalogValidationMessage({ code: 'linked_project_unpublished', path: 'groups.small.choices.cupping' }), /拔罐|引用项目|未发布/);
});

test('价格预览只选择启用项并满足每个选项组的数量约束', () => {
  const choiceIds = previewChoiceIds([
    {
      selection_mode: 'single', required: true, min_select: 0, max_select: 1,
      choices: [{ id: 11, status: 'active' }, { id: 12, status: 'inactive' }],
    },
    {
      selection_mode: 'multiple', required: false, min_select: 1, max_select: 2,
      choices: [{ id: 21, status: 'active' }, { id: 22, status: 'active' }, { id: 23, status: 'inactive' }],
    },
  ]);
  assert.deepEqual(choiceIds, [11, 21]);
});

test('价格预览金额按元展示并保留两位小数', () => {
  assert.equal(formatCents(3990), '¥39.90');
  assert.equal(formatCents(undefined), '-');
});

test('周二价格预览使用门店时区的周二日期', () => {
  const iso = nextTuesdayIso('Asia/Shanghai');
  assert.equal(new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Shanghai', weekday: 'short' }).format(new Date(iso)), 'Tue');
});

test('专属收费编辑回填固定按门店、团购、会员顺序排列价格', () => {
  const values = optionChoiceFormValues({
    code: 'oil', name: '草本精油', choice_type: 'dedicated_charge', charge_mode: 'custom_price',
    prices: [
      { price_type: 'member', amount_cents: 2500 },
      { price_type: 'store', amount_cents: 3000 },
      { price_type: 'group', amount_cents: 2800 },
    ],
  });
  assert.deepEqual(values.prices?.map((price) => [price.price_type, price.amount_cents]), [
    ['store', 3000], ['group', 2800], ['member', 2500],
  ]);
});

void ({} as OptionChoiceForm);

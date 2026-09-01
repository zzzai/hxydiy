import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

import {
  FEEDBACK_TAGS,
  customerLoginCopy,
  projectDetailActionLabel,
  shouldShowMembershipPromos,
  shouldShowCouponPrompt,
  shouldShowCouponTab,
  customerOptionDescription,
  customerPageSubtitle,
  customerPreferenceLabel,
  customerPreferenceNote,
  footBathBundleCopy,
  preferenceSummary,
  selectionPriceDisplay,
  serviceFeedbackAction,
  selectionSettlementNote,
} from '../src/customerCopy.ts';

test('顾客端副标题不显示自由搭配内部话术', () => {
  assert.equal(customerPageSubtitle('按需要，自由搭配'), '到店先一杯');
});

test('会员首页不展示会员卡推荐，非会员保留自愿办理入口', () => {
  assert.equal(shouldShowMembershipPromos(true), false);
  assert.equal(shouldShowMembershipPromos(false), true);
});
import type { PricingPreview } from '../src/domain.ts';

const preview: PricingPreview = {
  storeSubtotalCents: 17790,
  memberSubtotalCents: 12790,
  storeAdjustmentCents: 0,
  memberAdjustmentCents: 0,
  storeTotalCents: 17790,
  memberTotalCents: 12790,
  qualified: false,
};

test('选项说明移除到店确认等内部词并保留真实时长或体验描述', () => {
  assert.equal(customerOptionDescription('15分钟 · 到店确认', 15), '约15分钟');
  assert.equal(customerOptionDescription('到店确认部位', 30), '约30分钟');
  assert.equal(customerOptionDescription('', 30), '约30分钟');
  assert.equal(customerOptionDescription('舒缓花香', 90), '舒缓花香');
});

test('服务偏好摘要使用自然并列句并明确不加价', () => {
  assert.equal(preferenceSummary(['精油', '手法力度']), '请选择精油和手法力度，均不加价');
  assert.equal(preferenceSummary(['力度']), '请选择力度，不加价');
});

test('旧目录偏好标题和说明转成顾客熟悉的选购语言', () => {
  assert.equal(customerPreferenceLabel('草本偏好'), '泡脚液');
  assert.equal(customerPreferenceLabel('力度偏好'), '手法力度');
  assert.equal(customerPreferenceLabel('服务侧重'), '放松重点');
  assert.equal(customerPreferenceNote('到店确认'), '请选择一项 · 不加价');
  assert.equal(customerPreferenceNote('到店沟通'), '按偏好选择 · 不加价');
});

test('泡脚减免按0、1、2个不同部位和当前价格带生成行动文案', () => {
  assert.deepEqual(footBathBundleCopy(preview, [], false), {
    title: '选2个不同部位，基础泡脚费可免',
    detail: '局部加强按所选部位计费',
    value: '0/2',
  });
  assert.equal(
    footBathBundleCopy(preview, ['肩颈'], false).title,
    '再选1个不同部位，基础泡脚费可免',
  );
  assert.deepEqual(footBathBundleCopy({
    ...preview,
    qualified: true,
    storeAdjustmentCents: -3990,
    memberAdjustmentCents: -2990,
  }, ['肩颈', '腰臀'], false), {
    title: '已免基础泡脚费',
    detail: '已选2个不同部位',
    value: '-¥39.9',
  });
  assert.equal(footBathBundleCopy({
    ...preview,
    qualified: true,
    storeAdjustmentCents: -3990,
    memberAdjustmentCents: -2990,
  }, ['肩颈', '腰臀'], true).value, '-¥29.9');
});

test('结算说明区分编辑状态和门店已确认状态', () => {
  assert.equal(selectionSettlementNote(false), '服务完成后统一线下结算，最终以门店确认的服务清单为准');
  assert.equal(selectionSettlementNote(true), '已由门店确认，以门店最终清单为准');
});

test('详情页底部只提供加入或保存动作，删除统一在已选清单处理', () => {
  assert.equal(projectDetailActionLabel(false, false, false), '加入本次服务');
  assert.equal(projectDetailActionLabel(true, false, false), '保存本次选择');
  assert.equal(projectDetailActionLabel(false, false, true), '请先选完服务偏好');
  assert.equal(projectDetailActionLabel(true, true, false), '已提交前台');
});

test('会员详情页不展示普通券入口，固定套盒也不展示券入口', () => {
  assert.equal(shouldShowCouponPrompt(true, false), false);
  assert.equal(shouldShowCouponPrompt(false, true), false);
  assert.equal(shouldShowCouponPrompt(false, false), true);
});

test('非会员优惠券提示不承诺自动抵扣，明确以门店结算为准', () => {
  const detail = fs.readFileSync(new URL('../src/components/ProjectDetailPage.tsx', import.meta.url), 'utf8');
  const dialog = fs.readFileSync(new URL('../src/components/CouponLoginDialog.tsx', import.meta.url), 'utf8');
  assert.match(detail, /登录后领取，优惠以门店结算为准/);
  assert.match(dialog, /优惠以门店最终结算为准/);
  assert.doesNotMatch(detail, /满足条件自动抵扣/);
});

test('会员个人中心不展示领券入口', () => {
  assert.equal(shouldShowCouponTab(true), false);
  assert.equal(shouldShowCouponTab(false), true);
});

test('局部推拿在列表和详情页使用最新菜单名称', () => {
  const app = fs.readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  const detail = fs.readFileSync(new URL('../src/components/LocalDetailPage.tsx', import.meta.url), 'utf8');
  assert.match(app, /<h3>\{displayProjectName\(localProject\)\}<\/h3>/);
  assert.match(detail, /displayProjectName\(project\)/);
  assert.match(detail, /局部推拿服务/);
});

test('价格展示使用门店价，并为非会员单独提示会员价', () => {
  assert.deepEqual(selectionPriceDisplay(false, 23690, 19800, 23690), {
    primaryLabel: '门店价',
    memberHint: '会员价 ¥198',
    savingCents: 3890,
    originalHint: null,
    realizedSavingCents: 0,
  });
  assert.deepEqual(selectionPriceDisplay(true, 19800, 19800, 23690), {
    primaryLabel: '会员价',
    memberHint: null,
    savingCents: 0,
    originalHint: '门店价 ¥236.9',
    realizedSavingCents: 3890,
  });
  assert.deepEqual(selectionPriceDisplay(false, 23600, 23600, 23600), {
    primaryLabel: '门店价',
    memberHint: null,
    savingCents: 0,
    originalHint: null,
    realizedSavingCents: 0,
  });
});

test('提交成功页只在服务完成后提供评价入口', () => {
  assert.equal(serviceFeedbackAction(false, false), null);
  assert.equal(serviceFeedbackAction(true, false), '评价本次服务');
  assert.equal(serviceFeedbackAction(true, true), '已完成评价');
});

test('提交前已选弹层同时展示服务位置和当前身份确认', () => {
  const source = fs.readFileSync(new URL('../src/components/SelectionSummarySheet.tsx', import.meta.url), 'utf8');
  assert.match(source, /服务位置/);
  assert.match(source, /当前身份/);
});

test('登录入口先表达顾客收益，不使用系统保存口吻', () => {
  assert.deepEqual(customerLoginCopy('profile'), {
    title: '登录后，服务记录随时可查',
    detail: '查看本次清单、服务进度和评价，优惠券也会跟着账号走。',
    action: '登录查看记录',
  });
  assert.deepEqual(customerLoginCopy('record'), {
    title: '登录后，本次服务记录不丢',
    detail: '可随时查看本次清单、服务进度和评价。',
    action: '登录并查看记录',
  });
});

test('评价快捷标签覆盖技术、环境、技师和力度', () => {
  assert.deepEqual(FEEDBACK_TAGS, ['技术专业', '环境舒适', '技师细致', '力度合适', '整体放松']);
});

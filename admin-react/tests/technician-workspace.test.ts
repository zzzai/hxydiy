import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { dataProvider } from '../src/core/dataProvider/index.ts';
import { resources } from '../src/core/resources/index.ts';
import { buildServiceReferenceDisplay } from '../src/serviceReferenceDisplay.ts';


test('技师服务单通过严格的只读资源端点加载', async () => {
  assert.equal(resources.technicianServiceOrders, 'admin/v2/service-orders');
  let captured: any;
  const original = dataProvider.request;
  dataProvider.request = async (config: any) => {
    captured = config;
    return { data: { items: [], total: 0, page: 1, page_size: 30 } };
  };
  await dataProvider.getList(resources.technicianServiceOrders, { status: 'history', page: 1, page_size: 30 });
  assert.equal(captured.method, 'GET');
  assert.equal(captured.url, 'admin/v2/service-orders');
  assert.deepEqual(captured.params, { status: 'history', page: 1, page_size: 30 });
  dataProvider.request = original;
});

test('移动技师今日页读取服务位任务以保留画像关联字段', () => {
  const source = readFileSync(new URL('../src/technician/TechnicianTodayPage.tsx', import.meta.url), 'utf8');
  assert.match(source, /getTechnicianTasks/);
  assert.match(source, /selection_session_id/);
  assert.match(source, /completed_by_me/);
  assert.doesNotMatch(source, /getTechnicianServiceOrders/);
});

test('移动技师首页按沙发和房间区位展示全部服务位并使用状态色', () => {
  const source = readFileSync(new URL('../src/technician/TechnicianTodayPage.tsx', import.meta.url), 'utf8');
  assert.match(source, /technicianBoardGroups/);
  assert.match(source, /technicianPositionTone/);
  assert.match(source, /room_name/);
  assert.match(source, /occupancy_status/);
  assert.doesNotMatch(source, /filter\(\(task: any\) => task\.occupancy_status !== 'available'\)/);
});

test('移动技师首页将同一房间的多活动占用显式显示为待核对冲突', () => {
  const todaySource = readFileSync(new URL('../src/technician/TechnicianTodayPage.tsx', import.meta.url), 'utf8');
  const mobileSource = readFileSync(new URL('../src/technician/technicianMobile.ts', import.meta.url), 'utf8');
  assert.match(todaySource, /conflict_count/);
  assert.match(todaySource, /selectedOrder\.conflict/);
  assert.match(mobileSource, /conflict/);
});

test('移动技师服务参考提交完成服务关联和 v3 单一载荷', () => {
  const source = readFileSync(new URL('../src/technician/TechnicianProfileSheet.tsx', import.meta.url), 'utf8');
  assert.match(source, /createCustomerProfileRecord/);
  assert.match(source, /selection_session_id/);
  assert.match(source, /buildServiceReferenceV3Payload/);
  assert.match(source, /customerConfirmed/);
});

test('移动技师快记使用快捷服务字段并防止重复保存', () => {
  const source = readFileSync(new URL('../src/technician/TechnicianProfileSheet.tsx', import.meta.url), 'utf8');
  for (const field of ['age_range', 'gender', 'body_type', 'name="occupation"']) assert.doesNotMatch(source, new RegExp(field));
  for (const field of ['focusAreas', 'avoidAreas', 'forcePreference', 'temperaturePreference', 'serviceFeedback', 'nextVisitPlan']) assert.match(source, new RegExp(field));
  assert.match(source, /name="focusAreas"/);
  assert.match(source, /name="avoidAreas"/);
  assert.match(source, /maxLength=\{100\}/);
  assert.match(source, /confirmation === true/);
  assert.match(source, /saving/);
  assert.match(source, /disabled=\{saving\}/);
  assert.match(source, /暂不记录/);
  assert.match(source, /lastPayloadSignature/);
  assert.match(source, /JSON\.stringify/);
});

test('活动顾客服务单显式打开安全服务参考摘要', () => {
  const today = readFileSync(new URL('../src/technician/TechnicianTodayPage.tsx', import.meta.url), 'utf8');
  const drawer = readFileSync(new URL('../src/technician/TechnicianServiceReferenceDrawer.tsx', import.meta.url), 'utf8');
  assert.match(today, /查看上次服务参考/);
  assert.match(today, /TechnicianServiceReferenceDrawer/);
  assert.match(drawer, /getTechnicianServiceReference/);
  assert.match(drawer, /请本次服务前再次确认/);
  for (const sensitive of ['quote', 'note', 'phone', 'age_range', 'gender', 'occupation']) assert.doesNotMatch(drawer, new RegExp(sensitive));
});

test('画像写入请求附带幂等键', () => {
  const source = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8');
  const start = source.indexOf('export const createCustomerProfileRecord');
  assert.ok(start >= 0, '找不到画像写入 API');
  const nextExport = source.indexOf('\nexport const ', start + 1);
  assert.match(source.slice(start, nextExport > start ? nextExport : undefined), /Idempotency-Key/);
});

test('管理端将 v3 服务参考显示为结构化摘要而非普通运营标签', () => {
  const source = readFileSync(new URL('../src/pages/SelectionSessionsPage.tsx', import.meta.url), 'utf8');
  assert.match(source, /buildServiceReferenceDisplay/);
  assert.match(source, /customer_confirmed/);
  assert.match(source, /confirmed_at/);
  assert.doesNotMatch(source, /addUserTag\(/);
  assert.doesNotMatch(source, /createCustomerProfileRecord/);
  assert.doesNotMatch(source, /addUserTag|searchIndex|algorithmFeature/);
});

test('管理端以白名单结构化展示 v3 且原话保持默认折叠', () => {
  const display = buildServiceReferenceDisplay({
    schema_version: 3, taxonomy_version: 'service_reference_v2', customer_confirmed: true,
    profile: {
      customer_reported: { personal_context: { build: 'balanced' }, service_related_context: { contexts: ['medication_mentioned'], quote: '顾客自述正在用药' } },
      technician_observed: { session_response: { relaxation: 'quick' } }, next_visit: { plan: 'confirm_on_arrival' },
    },
  });
  assert.equal(display.version, 'v3 · service_reference_v2');
  assert.deepEqual(display.groups, [
    { title: '个人概况', items: [{ label: '体型', value: '匀称' }] },
    { title: '服务相关情况', items: [{ label: '需再次确认', value: '顾客提及正在用药' }] },
    { title: '本次反应', items: [{ label: '放松过程', value: '较快' }] },
    { title: '下次与沟通', items: [{ label: '下次建议', value: '到店再确认' }] },
  ]);
  assert.equal(display.collapsedQuote, '顾客自述正在用药');
  assert.doesNotMatch(JSON.stringify(display.groups), /顾客自述正在用药/);
});

test('管理端兼容 v2 嵌套服务参考而不退化为空摘要', () => {
  const display = buildServiceReferenceDisplay({
    schema_version: 2, taxonomy_version: 'service_reference_v1', customer_confirmed: false,
    profile: {
      customer_reported: { focus_areas: ['neck_shoulder'], avoid_areas: ['abdomen'], force_preference: 'medium', temperature_preference: 'higher', quote: '顾客希望避开腹部' },
      technician_observed: { service_feedback: 'better_after_adjustment' }, next_visit: { plan: 'repeat_current' },
    },
  });
  assert.equal(display.version, 'v2 · service_reference_v1');
  assert.deepEqual(display.groups, [
    { title: '服务偏好', items: [{ label: '本次重点', value: '肩颈' }, { label: '避开或谨慎', value: '腹部' }, { label: '力度', value: '适中' }, { label: '温度', value: '偏高' }] },
    { title: '本次反应', items: [{ label: '服务反馈', value: '调整后更合适' }] },
    { title: '下次与沟通', items: [{ label: '下次建议', value: '延续本次' }] },
  ]);
  assert.equal(display.collapsedQuote, '顾客希望避开腹部');
});

import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { dataProvider } from '../src/core/dataProvider/index.ts';
import { resources } from '../src/core/resources/index.ts';


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

test('移动技师服务参考提交完成服务关联和 v2 字段', () => {
  const source = readFileSync(new URL('../src/technician/TechnicianProfileSheet.tsx', import.meta.url), 'utf8');
  assert.match(source, /createCustomerProfileRecord/);
  assert.match(source, /selection_session_id/);
  assert.match(source, /buildServiceReferencePayload/);
  assert.match(source, /customerConfirmed/);
});

test('移动技师快记使用快捷服务字段并防止重复保存', () => {
  const source = readFileSync(new URL('../src/technician/TechnicianProfileSheet.tsx', import.meta.url), 'utf8');
  for (const field of ['age_range', 'gender', 'body_type', 'occupation']) assert.doesNotMatch(source, new RegExp(field));
  for (const field of ['focusAreas', 'avoidAreas', 'forcePreference', 'temperaturePreference', 'serviceFeedback', 'nextVisitPlan']) assert.match(source, new RegExp(field));
  assert.match(source, /name="focusAreas"/);
  assert.match(source, /name="avoidAreas"/);
  assert.match(source, /maxLength=\{100\}/);
  assert.match(source, /customerConfirmed: false/);
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

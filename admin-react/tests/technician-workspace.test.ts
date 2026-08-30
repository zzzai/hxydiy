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

test('移动技师画像提交完成服务关联和画像字段', () => {
  const source = readFileSync(new URL('../src/technician/TechnicianProfileSheet.tsx', import.meta.url), 'utf8');
  assert.match(source, /createCustomerProfileRecord/);
  assert.match(source, /selection_session_id/);
  assert.match(source, /profile:/);
  assert.match(source, /signals:/);
});

test('移动技师快记在首屏展示结构化基础信息并防止重复保存', () => {
  const source = readFileSync(new URL('../src/technician/TechnicianProfileSheet.tsx', import.meta.url), 'utf8');
  for (const field of ['age_range', 'gender', 'body_type', 'occupation']) assert.match(source, new RegExp(`name=\\"${field}\\"`));
  assert.match(source, /source/);
  assert.match(source, /saving/);
  assert.match(source, /disabled=\{saving\}/);
  assert.match(source, /暂不记录/);
});

test('画像写入请求附带幂等键', () => {
  const source = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8');
  const start = source.indexOf('export const createCustomerProfileRecord');
  assert.ok(start >= 0, '找不到画像写入 API');
  const nextExport = source.indexOf('\nexport const ', start + 1);
  assert.match(source.slice(start, nextExport > start ? nextExport : undefined), /Idempotency-Key/);
});

test('管理端画像快记沿用技师安全字段契约', () => {
  const source = readFileSync(new URL('../src/pages/SelectionSessionsPage.tsx', import.meta.url), 'utf8');
  for (const signal of ['肩颈紧张', '腰部不适', '腿部酸胀', '局部紧绷', '放松需求']) {
    assert.match(source, new RegExp(signal));
  }
  for (const legacySignal of ['局部硬结', '首次到店', '重点维护']) {
    assert.doesNotMatch(source, new RegExp(legacySignal));
  }
  assert.match(source, /'18-25'/);
  assert.doesNotMatch(source, /'18-25岁'/);
  assert.match(source, /maxLength=\{500\}/);
});

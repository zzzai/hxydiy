import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
  buildKioskUrl,
  countPositionStates,
  getForceReleaseTargets,
  getPositionActions,
  occupancyStatusMeta,
  positionTypeLabel,
  splitPositionGroups,
  waitingReleaseMeta,
  normalizeServicePositions,
  DEFAULT_SERVICE_POSITION_LAYOUT,
} from '../src/servicePositions.ts';

test('服务位按大厅沙发和房间床位分组展示', () => {
  const base = { state: 'available', operational_status: 'active' } as any;
  const positions = [
    { ...base, id: 1, type: 'sofa', name: '1号沙发' },
    { ...base, id: 2, type: 'bed', name: '1号房间 A 床' },
    { ...base, id: 3, type: 'room', name: '理疗房' },
  ];
  const groups = splitPositionGroups(positions);
  assert.deepEqual(groups.sofas.map(item => item.id), [1]);
  assert.deepEqual(groups.rooms.map(item => item.id), [2, 3]);
  assert.equal(positionTypeLabel('sofa'), '大厅沙发');
  assert.equal(positionTypeLabel('bed'), '房间床位');
  assert.equal(positionTypeLabel('room'), '独立房间');
});

const waitingOccupancy = {
  id: 1,
  store_id: 1,
  room_id: 1,
  selection_session_id: 'waiting-session',
  active_room_id: 1,
  status: 'waiting_service' as const,
  source: 'personal_qr',
  hold_expires_at: null,
  retained_until: null,
  expected_end_at: null,
  actual_start_at: null,
  actual_service_end_at: null,
  departed_at: null,
  released_at: null,
  release_reason: '',
  version: 1,
};

test('活动服务位只显示当前状态允许的门店动作', () => {
  assert.deepEqual(getPositionActions('held', 'staff'), []);
  assert.deepEqual(getPositionActions('waiting_service', 'manager'), ['start_service']);
  assert.deepEqual(getPositionActions('in_service', 'manager'), ['finish_service']);
  assert.deepEqual(getPositionActions('post_service_present', 'staff'), []);
  assert.deepEqual(getPositionActions('cleaning', 'staff'), []);
});

test('只有未转服务单的待确认服务位允许前台续留', () => {
  assert.deepEqual(
    getPositionActions('waiting_service', 'manager', false, null, false, 'submitted'),
    ['start_service'],
  );
  assert.equal(
    getPositionActions('waiting_service', 'staff', false, null, false, 'confirmed').includes('retain'),
    false,
  );
  assert.equal(
    getPositionActions('waiting_service', 'staff', true, 'draft', false, 'submitted').includes('retain'),
    false,
  );
});

test('待服务提醒按默认或续留截止时间稳定分级', () => {
  const submittedAt = '2026-08-18T00:00:00.000Z';
  const atMinute = (minute: number) => Date.parse(submittedAt) + minute * 60_000;

  assert.equal(waitingReleaseMeta(waitingOccupancy, 'submitted', submittedAt, atMinute(29)).level, 'normal');
  assert.equal(waitingReleaseMeta(waitingOccupancy, 'submitted', submittedAt, atMinute(30)).level, 'warning');
  assert.equal(waitingReleaseMeta(waitingOccupancy, 'submitted', submittedAt, atMinute(50)).level, 'urgent');
  assert.equal(waitingReleaseMeta(waitingOccupancy, 'submitted', submittedAt, atMinute(60)).level, 'overdue');

  const retained = { ...waitingOccupancy, retained_until: '2026-08-18T01:30:00.000Z' };
  const retainedMeta = waitingReleaseMeta(retained, 'submitted', submittedAt, atMinute(60));
  assert.equal(retainedMeta.level, 'warning');
  assert.equal(retainedMeta.dueAt, retained.retained_until);
  assert.equal(retainedMeta.remainingMs, 30 * 60_000);
});

test('前台已确认后不再展示自动释放倒计时', () => {
  assert.deepEqual(
    waitingReleaseMeta(waitingOccupancy, 'confirmed', '2026-08-18T00:00:00.000Z', Date.parse('2026-08-18T02:00:00.000Z')),
    {
      level: 'confirmed',
      label: '前台已确认，等待开始服务',
      dueAt: null,
      remainingMs: null,
    },
  );
});

test('服务结束后不在 DIY 侧继续操作沙发释放', () => {
  assert.deepEqual(getPositionActions('post_service_present', 'staff', false), []);
  assert.deepEqual(getPositionActions('post_service_present', 'staff', true), []);
});

test('管理员在现场异常状态可以强制释放', () => {
  assert.deepEqual(getPositionActions('in_service', 'admin'), ['finish_service']);
  assert.deepEqual(getPositionActions('cleaning', 'admin'), []);
});

test('异常结束进入清洁后仍可先完成异常结算', () => {
  assert.deepEqual(
    getPositionActions('cleaning', 'admin', false, null, true),
    [],
  );
});

test('强制释放根据现场状态限制为直接释放或进入清洁', () => {
  assert.deepEqual(getForceReleaseTargets('held'), ['released']);
  assert.deepEqual(getForceReleaseTargets('waiting_service'), ['released', 'cleaning']);
  assert.deepEqual(getForceReleaseTargets('in_service'), ['cleaning']);
  assert.deepEqual(getForceReleaseTargets('post_service_present'), ['cleaning']);
});

test('已转服务单的服务位不显示调整位置动作', () => {
  assert.deepEqual(
    getPositionActions('waiting_service', 'staff', true, 'draft'),
    [],
  );
  assert.deepEqual(
    getPositionActions('in_service', 'admin', true, 'in_service'),
    [],
  );
  assert.deepEqual(
    getPositionActions('post_service_present', 'admin', true, 'completed'),
    [],
  );
  assert.deepEqual(
    getPositionActions('cleaning', 'admin', true, 'completed'),
    [],
  );
});

test('服务位状态使用门店可理解的中文名称', () => {
  assert.equal(occupancyStatusMeta('available').label, '可用');
  assert.equal(occupancyStatusMeta('post_service_present').label, '服务完成·仍在位');
  assert.equal(occupancyStatusMeta('cleaning').label, '待清洁');
});

test('服务位看板按现场状态统计，不把停用位算作可用', () => {
  const counts = countPositionStates([
    { state: 'available' },
    { state: 'available' },
    { state: 'held' },
    { state: 'waiting_service' },
    { state: 'in_service' },
    { state: 'post_service_present' },
    { state: 'cleaning' },
    { state: 'unavailable' },
  ]);
  assert.deepEqual(counts, {
    available: 2,
    held: 1,
    waiting_service: 1,
    in_service: 1,
    attention: 2,
    unavailable: 1,
  });
});

test('共享 iPad 链接包含一次性会话且不依赖管理端路由', () => {
  const link = buildKioskUrl('http://127.0.0.1:4180/diy/', 3, 'session-a', 'token-a');
  const url = new URL(link);
  assert.equal(url.pathname, '/diy/');
  assert.equal(url.searchParams.get('store'), '3');
  assert.equal(url.searchParams.get('session'), 'session-a');
  assert.equal(url.searchParams.get('token'), 'token-a');
  assert.equal(url.searchParams.get('source'), 'kiosk');
});

test('服务位弹窗使用当前 Ant Design 销毁属性', () => {
  const source = readFileSync(new URL('../src/pages/ServicePositionsPage.tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(source, /destroyOnClose/);
  assert.match(source, /destroyOnHidden/);
});

test('服务位页面不暴露结算或收款入口', () => {
  const source = readFileSync(new URL('../src/pages/ServicePositionsPage.tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(source, /settleSelectionSession|openSettlement|submitSettlement|settle_selection/);
  assert.doesNotMatch(source, /服务结算|完成结算|收款方式|实收金额/);
});

test('服务位动作仅允许店长和管理员，普通员工与技师不可执行', () => {
  assert.deepEqual(getPositionActions('waiting_service', 'manager'), ['start_service']);
  assert.deepEqual(getPositionActions('in_service', 'admin'), ['finish_service']);
  assert.deepEqual(getPositionActions('waiting_service', 'staff'), []);
  assert.deepEqual(getPositionActions('in_service', 'technician'), []);
});

test('异常服务位响应仍按服务位编码和类型补齐 8 沙发与 9 床位', () => {
  const malformed = DEFAULT_SERVICE_POSITION_LAYOUT.map((item, id) => ({
    id: id + 1, code: item.code, type: item.type === 'sofa' ? 'bed' : 'sofa', name: '错误类型',
  })) as any;
  const normalized = normalizeServicePositions(malformed);
  assert.equal(normalized.filter((item) => item.type === 'sofa').length, 8);
  assert.equal(normalized.filter((item) => item.type === 'bed').length, 9);
  assert.equal(new Set(normalized.map((item) => item.code)).size, 17);
});

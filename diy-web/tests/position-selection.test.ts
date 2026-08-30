import assert from 'node:assert/strict';
import test from 'node:test';

import type { ServicePosition } from '../src/api.ts';
import {
  getEntrySource,
  getPositionSelectionDecision,
  resolveEntryConflict,
  resolveActivePositionCode,
  resolveRequestedPosition,
  shouldResumeCurrentPosition,
} from '../src/positionSelection.ts';

function position(overrides: Partial<ServicePosition> = {}): ServicePosition {
  return {
    id: 2,
    code: 'sofa-02',
    name: '2号沙发',
    customer_label: '2号沙发',
    type: 'sofa',
    state: 'available',
    is_current: false,
    customer_selectable: true,
    operational_status: 'active',
    map_x: 0,
    map_y: 0,
    map_width: 0.2,
    map_height: 0.1,
    sort_order: 2,
    occupancy: null,
    ...overrides,
  };
}

test('门店入口选位使用 store_qr，服务位专属二维码仍保留强绑定来源', () => {
  assert.equal(getEntrySource({ positionCode: 'sofa-06' }), 'store_qr');
  assert.equal(getEntrySource({ positionCode: 'sofa-06', qrToken: 'signed-token' }), 'personal_qr');
  assert.equal(getEntrySource({ positionCode: 'room-01', qrToken: 'signed-token' }), 'room_qr');
  assert.equal(getEntrySource({ positionCode: 'sofa-06', source: 'kiosk' }), 'kiosk');
});

test('首次入店时只有真正可运营且可由顾客选择的空闲沙发可进入', () => {
  assert.deepEqual(getPositionSelectionDecision(position(), { mode: 'entry' }), {
    selectable: true,
    label: '可选择',
    reason: '点击进入 2号沙发',
  });
  assert.equal(getPositionSelectionDecision(position({ customer_selectable: false }), { mode: 'entry' }).selectable, false);
  assert.equal(getPositionSelectionDecision(position({ operational_status: 'maintenance' }), { mode: 'entry' }).label, '暂停使用');
  assert.equal(getPositionSelectionDecision(position({ state: 'unavailable' }), { mode: 'entry' }).label, '暂停使用');
});

test('占用生命周期的每种状态都有明确且不可误点的提示', () => {
  const expected = {
    held: '已临时占用',
    waiting_service: '待服务',
    in_service: '服务中',
    post_service_present: '服务已结束',
    cleaning: '清洁中',
  } as const;

  for (const [state, label] of Object.entries(expected)) {
    const decision = getPositionSelectionDecision(position({ state: state as ServicePosition['state'] }), { mode: 'entry' });
    assert.equal(decision.selectable, false);
    assert.equal(decision.label, label);
    assert.notEqual(decision.reason, '');
  }
});

test('个人二维码临时占位期间可以换到空闲沙发', () => {
  assert.equal(getPositionSelectionDecision(position(), {
    mode: 'move',
    source: 'personal_qr',
    currentType: 'sofa',
    occupancyStatus: 'held',
  }).selectable, true);
});

test('共享设备、房间、已提交、服务中和服务结束后均要求前台换位', () => {
  const contexts = [
    { mode: 'move' as const, source: 'kiosk', currentType: 'sofa', occupancyStatus: 'held' },
    { mode: 'move' as const, source: 'room_qr', currentType: 'room', occupancyStatus: 'held' },
    { mode: 'move' as const, source: 'personal_qr', currentType: 'sofa', occupancyStatus: 'waiting_service' },
    { mode: 'move' as const, source: 'personal_qr', currentType: 'sofa', occupancyStatus: 'in_service' },
    { mode: 'move' as const, source: 'personal_qr', currentType: 'sofa', occupancyStatus: 'post_service_present' },
    { mode: 'move' as const, source: 'personal_qr', currentType: 'sofa', occupancyStatus: 'cleaning' },
    { mode: 'move' as const, source: 'personal_qr', currentType: 'sofa', occupancyStatus: 'released' },
  ];

  for (const context of contexts) {
    const decision = getPositionSelectionDecision(position(), context);
    assert.equal(decision.selectable, false);
    assert.match(decision.reason, /前台|刷新/);
  }

  assert.equal(getPositionSelectionDecision(position(), contexts[2]).reason, '已提交前台，如需换位请联系前台');
});

test('当前位置和正在提交的换位请求不会被重复点击', () => {
  assert.equal(getPositionSelectionDecision(position({ is_current: true }), {
    mode: 'move', source: 'personal_qr', currentType: 'sofa', occupancyStatus: 'held',
  }).label, '当前位置');
  assert.equal(getPositionSelectionDecision(position(), {
    mode: 'move', source: 'personal_qr', currentType: 'sofa', occupancyStatus: 'held', moving: true,
  }).label, '正在切换');
});

test('入店并发冲突会刷新沙发图，旧设备占用会恢复原服务位', () => {
  assert.deepEqual(resolveEntryConflict('POSITION_OCCUPIED'), { action: 'refresh-map' });
  assert.deepEqual(resolveEntryConflict('POSITION_UNAVAILABLE'), { action: 'refresh-map' });
  assert.deepEqual(resolveEntryConflict('', undefined, 404), { action: 'refresh-map' });
  assert.deepEqual(resolveEntryConflict('BROWSER_ACTIVE_ELSEWHERE', 'sofa-05'), {
    action: 'resume-current',
    positionCode: 'sofa-05',
  });
  assert.deepEqual(resolveEntryConflict('BROWSER_ACTIVE_ELSEWHERE'), { action: 'show-error' });
  assert.deepEqual(resolveEntryConflict('UNKNOWN'), { action: 'show-error' });
});

test('明确的二维码服务位编码优先于服务端旧 is_current 标记', () => {
  const requested = position({ code: 'sofa-05', customer_label: '5号沙发', is_current: false });
  const staleCurrent = position({ code: 'sofa-06', customer_label: '6号沙发', is_current: true });
  assert.equal(resolveRequestedPosition([staleCurrent, requested], 'sofa-05')?.code, 'sofa-05');
  assert.equal(resolveRequestedPosition([staleCurrent, requested], '')?.code, 'sofa-06');
});

test('明确二维码服务位遇到浏览器已有会话时不恢复到旧服务位', () => {
  const conflict = resolveEntryConflict('BROWSER_ACTIVE_ELSEWHERE', 'sofa-06');
  assert.equal(shouldResumeCurrentPosition({
    requestedCode: 'sofa-05',
    qrToken: undefined,
    conflict,
  }), false);
  assert.equal(shouldResumeCurrentPosition({
    requestedCode: '',
    qrToken: undefined,
    conflict,
  }), true);
});

test('手动换位后当前服务位编码优先于首次二维码编码', () => {
  assert.equal(resolveActivePositionCode('sofa-07', 'sofa-05'), 'sofa-07');
  assert.equal(resolveActivePositionCode('', 'sofa-05'), 'sofa-05');
});

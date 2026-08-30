import assert from 'node:assert/strict';
import test from 'node:test';
import { TECHNICIAN_MOBILE_ROUTES, technicianActions, technicianBoardGroups, technicianOrderItemLabel, technicianPositionTone, technicianStatusLabel } from '../src/technician/technicianMobile.ts';

test('移动技师端只暴露三栏业务路由', () => {
  assert.deepEqual(TECHNICIAN_MOBILE_ROUTES, ['/technician/today', '/technician/history', '/technician/me']);
});

test('技师状态使用现场可理解文案', () => {
  assert.equal(technicianStatusLabel('available'), '空闲');
  assert.equal(technicianStatusLabel('waiting_service'), '待确认');
  assert.equal(technicianStatusLabel('in_service'), '服务中');
  assert.equal(technicianStatusLabel('post_service_present'), '已完成');
});

test('服务状态只显示允许的主操作', () => {
  assert.deepEqual(technicianActions('available'), []);
  assert.deepEqual(technicianActions('waiting_service'), ['confirm']);
  assert.deepEqual(technicianActions('in_service'), ['finish']);
  assert.deepEqual(technicianActions('post_service_present'), ['profile']);
  assert.deepEqual(technicianActions('released'), []);
});

test('服务位状态使用一眼可区分的颜色语义', () => {
  assert.equal(technicianPositionTone('available'), 'idle');
  assert.equal(technicianPositionTone('waiting_service'), 'waiting');
  assert.equal(technicianPositionTone('in_service'), 'serving');
  assert.equal(technicianPositionTone('post_service_present'), 'finished');
});

test('局部调理在订单中使用局部简称展示顾客选择的部位', () => {
  assert.equal(technicianOrderItemLabel({ name: '局部调理', code: 'hxy-jubu-30', diy_preferences: ['肩颈'] }), '局部：肩颈');
  assert.equal(technicianOrderItemLabel({ name: '局部调理', code: 'hxy-jubu-30', diy_preferences: ['腰臀', '腹部'] }), '局部：腰臀、腹部');
  assert.equal(technicianOrderItemLabel({ name: '草本泡脚', code: 'hxy-qiqing-30', diy_preferences: ['老姜'] }), '草本泡脚');
});

test('技师看板按沙发和房间分组，保留顾客提交的服务位顺序', () => {
  const groups = technicianBoardGroups([
    { occupancy_id: 2, room_type: 'bed', room_name: '包间 02 A 床' },
    { occupancy_id: 1, room_type: 'sofa', room_name: '沙发 01' },
  ]);
  assert.deepEqual(groups.map((group) => group.label), ['沙发', '房间']);
  assert.equal(groups[0].items[0].room_name, '沙发 01');
  assert.equal(groups[1].items[0].room_name, '包间 02 A 床');
});

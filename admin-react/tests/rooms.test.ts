import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

import { getRoomOperationalAction, mergeRoomConfigurationData, roomConfigurationReducer } from '../src/rooms.ts';

test('opens room configuration in place and closes back to the board', () => {
  assert.equal(roomConfigurationReducer(null, { type: 'open', roomId: 12 }), 12);
  assert.equal(roomConfigurationReducer(12, { type: 'open', roomId: 18 }), 18);
  assert.equal(roomConfigurationReducer(18, { type: 'close' }), null);
});

test('keeps board metadata when assignment detail omits room fields', () => {
  assert.deepEqual(
    mergeRoomConfigurationData(
      { id: 1, name: '1号沙发', code: 'sofa-01', room_group: 'sofa', floor: '1F' },
      { id: 1, name: '1号沙发', code: 'sofa-01', technicians: [] },
    ),
    { id: 1, name: '1号沙发', code: 'sofa-01', room_group: 'sofa', floor: '1F', technicians: [] },
  );
});

test('exposes operational status action only for idle service positions', () => {
  assert.equal(getRoomOperationalAction({ is_service_position: true, operational_status: 'active', status: 'available' }), 'disable');
  assert.equal(getRoomOperationalAction({ is_service_position: true, operational_status: 'inactive', status: 'available' }), 'enable');
  assert.equal(getRoomOperationalAction({ is_service_position: true, operational_status: 'active', status: 'in_service' }), null);
  assert.equal(getRoomOperationalAction({ is_service_position: false, operational_status: 'active', status: 'available' }), null);
  assert.equal(getRoomOperationalAction({ is_space_container: true, operational_status: 'active', status: 'available' }), null);
});

test('房间配置页提供服务位停用和重新启用入口', () => {
  const source = readFileSync(new URL('../src/pages/RoomsPage.tsx', import.meta.url), 'utf8');
  assert.match(source, /updateServicePositionOperationalStatus/);
  assert.match(source, /停用服务位/);
  assert.match(source, /重新启用服务位/);
  assert.match(source, /operational_status/);
});

test('房态看板展示已停用统计而不是把停用位算作空闲', () => {
  const source = readFileSync(new URL('../src/pages/RoomsPage.tsx', import.meta.url), 'utf8');
  assert.match(source, /label: '已停用'/);
  assert.match(source, /stats\.inactive/);
});

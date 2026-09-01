import assert from 'node:assert/strict';
import test from 'node:test';

import { mergeRoomConfigurationData, roomConfigurationReducer } from '../src/rooms.ts';

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

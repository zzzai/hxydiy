import assert from 'node:assert/strict';
import test from 'node:test';
import { toggleBodyMapPoint } from '../src/technician/bodyMap.ts';

test('人体点位以顾客身体左右为准，可选择和取消同一部位', () => {
  const rightShoulder = { region: 'shoulder' as const, side: 'right' as const };
  const leftKnee = { region: 'knee' as const, side: 'left' as const };

  assert.deepEqual(toggleBodyMapPoint([], rightShoulder), [rightShoulder]);
  assert.deepEqual(toggleBodyMapPoint([rightShoulder], leftKnee), [rightShoulder, leftKnee]);
  assert.deepEqual(toggleBodyMapPoint([rightShoulder, leftKnee], rightShoulder), [leftKnee]);
});

test('人体点位最多三项，第四项不会覆盖既有选择', () => {
  const selected = [
    { region: 'shoulder' as const, side: 'right' as const },
    { region: 'knee' as const, side: 'left' as const },
    { region: 'lower_back' as const, side: 'center' as const },
  ];
  assert.deepEqual(toggleBodyMapPoint(selected, { region: 'ankle', side: 'right' }), selected);
});

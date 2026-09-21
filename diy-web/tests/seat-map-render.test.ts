import assert from 'node:assert/strict';
import test from 'node:test';

import type { ServicePosition } from '../src/api.ts';
import { groupSofasBySide } from '../src/seatMap.ts';

function sofa(code: string, label: string, x: number, y: number, order: number): ServicePosition {
  return {
    id: order, code, name: label, customer_label: label, type: 'sofa', state: 'available',
    is_current: false, customer_selectable: true, operational_status: 'active',
    map_x: x, map_y: y, map_width: 0.22, map_height: 0.14, sort_order: order, occupancy: null,
  };
}

test('服务位平面图按物理左右坐标展示沙发', () => {
  const positions = [
    sofa('sofa-01', '1号沙发', 0.08, 0.14, 1), sofa('sofa-02', '2号沙发', 0.08, 0.34, 2),
    sofa('sofa-03', '3号沙发', 0.08, 0.54, 3), sofa('sofa-04', '5号沙发', 0.08, 0.74, 4),
    sofa('sofa-05', '6号沙发', 0.70, 0.14, 5), sofa('sofa-06', '7号沙发', 0.70, 0.34, 6),
    sofa('sofa-07', '8号沙发', 0.70, 0.54, 7), sofa('sofa-08', '9号沙发', 0.70, 0.74, 8),
  ];
  const { left, right } = groupSofasBySide(positions);

  assert.deepEqual(left.map((position) => position.customer_label), ['1号沙发', '2号沙发', '3号沙发', '5号沙发']);
  assert.deepEqual(right.map((position) => position.customer_label), ['6号沙发', '7号沙发', '8号沙发', '9号沙发']);
});


import assert from 'node:assert/strict';
import test from 'node:test';
import { groupManagerPositionCards, projectManagerPositions, positionDetailMatches, sortManagerPositions } from '../src/technician/managerPositions.ts';
import type { ManagerPositionCard } from '../src/technician/managerPositions.ts';

function position(id = 1, status = 'in_service') {
  const selectionId = 'synthetic-selection-' + id;
  return { id, customer_label: id + '号沙发', name: 'Synthetic position', type: 'sofa',
    operational_status: 'active', sort_order: id, state: status,
    occupancy: { id: id + 100, store_id: 1, room_id: id, active_room_id: id,
      selection_session_id: selectionId, active_session_id: selectionId, status },
    selection: { id: selectionId, status: 'confirmed', source: 'in_store',
      items: [{ name: '草本泡', quantity: 1 }], pricing_snapshot: { payable_total_cents: 8900, applied_price_type: 'member' }, submitted_at: null },
  };
}
function map(positions: unknown[]) { return { store_id: 1, positions, updated_at: '2026-10-21T00:00:00+08:00' }; }

test('all returned positions are retained independently of order pagination or a fixed layout', () => {
  const result = projectManagerPositions(map(Array.from({ length: 25 }, (_, i) => position(i + 1))), 1);
  assert.equal(result.positions.length, 25);
  assert.equal(result.positions[24].name, '25号沙发');
  assert.equal(projectManagerPositions(map([]), 1).positions.length, 0);
});
test('wrong-store, malformed and duplicate maps fail instead of becoming empty availability', () => {
  assert.throws(() => projectManagerPositions(map([position()]), 2));
  assert.throws(() => projectManagerPositions({ store_id: 1 }, 1));
  assert.throws(() => projectManagerPositions(map([position(), position()]), 1));
});
test('no association is neutral and disabled positions keep a linked selection visible', () => {
  const empty = { ...position(1), occupancy: null, selection: null, state: 'available' };
  const disabled = { ...position(2), operational_status: 'inactive' };
  const result = projectManagerPositions(map([empty, disabled]), 1);
  assert.equal(result.positions[0].association, 'none');
  assert.equal(result.positions[0].statusLabel, '暂无当前选单');
  assert.equal(result.positions[1].enabled, false);
  assert.equal(result.positions[1].detail?.selectionId, 'synthetic-selection-2');
});
test('all ownership and current-association identifiers must match before revealing selection content', () => {
  for (const field of ['store_id', 'room_id', 'active_room_id', 'selection_session_id', 'active_session_id']) {
    const current = position();
    (current.occupancy as Record<string, unknown>)[field] = field.includes('session') ? 'other-selection' : 99;
    const result = projectManagerPositions(map([current]), 1).positions[0];
    assert.equal(result.association, 'unverified', field);
    assert.equal(result.detail, undefined, field);
  }
  const missing = position();
  delete (missing.occupancy as Record<string, unknown>).active_session_id;
  assert.equal(projectManagerPositions(map([missing]), 1).positions[0].detail, undefined);
});
test('ended service is not revived by a confirmed selection', () => {
  const result = projectManagerPositions(map([position(1, 'post_service_present'), position(2, 'cleaning')]), 1);
  assert.equal(result.positions[0].statusLabel, '已结束服务 · 待离位确认');
  assert.equal(result.positions[1].statusLabel, '已结束服务 · 清洁中');
  assert.ok(result.positions.every(item => item.detail?.selectionState === '已确认'));
});
test('zero snapshot is retained and missing price is never recomputed from reference totals', () => {
  const zero = position(1), missing = position(2);
  zero.selection.pricing_snapshot.payable_total_cents = 0;
  (missing.selection as any).pricing_snapshot = null;
  (missing.selection as any).member_total_cents = 12345;
  const result = projectManagerPositions(map([zero, missing]), 1);
  assert.equal(result.positions[0].detail?.price.value, '¥0');
  assert.equal(result.positions[1].detail?.price.value, '金额待核实');
});
test('detail identity requires the same position, occupancy and selection after refresh', () => {
  const first = projectManagerPositions(map([position(1)]), 1).positions[0];
  const key = first.detail!;
  assert.equal(positionDetailMatches(first, key), true);
  const changed = position(1); changed.occupancy.id = 999;
  assert.equal(positionDetailMatches(projectManagerPositions(map([changed]), 1).positions[0], key), false);
  const changedSelection = position(1);
  changedSelection.selection.id = changedSelection.occupancy.selection_session_id = changedSelection.occupancy.active_session_id = 'new-selection';
  assert.equal(positionDetailMatches(projectManagerPositions(map([changedSelection]), 1).positions[0], key), false);
  assert.equal(positionDetailMatches(undefined, key), false);
});

test('店长座位图按现场编号自然排序，不跟随错乱的 sort_order', () => {
  const cards = [
    ['sofa', '5号沙发'], ['sofa', '3号沙发'], ['sofa', '2号沙发'], ['sofa', '1号沙发'],
    ['sofa', '9号沙发'], ['sofa', '8号沙发'], ['sofa', '7号沙发'], ['sofa', '6号沙发'],
    ['bed', '2号房间 A 床'], ['bed', '1号房间 B 床'], ['bed', '1号房间 A 床'],
  ].map(([type, name], index): ManagerPositionCard => ({
    id: index + 1, name, type: type as ManagerPositionCard['type'], enabled: true,
    association: 'none', statusLabel: '暂无当前选单',
  }));
  assert.deepEqual(sortManagerPositions(cards).map(card => card.name), [
    '1号沙发', '2号沙发', '3号沙发', '5号沙发', '6号沙发', '7号沙发', '8号沙发', '9号沙发',
    '1号房间 A 床', '1号房间 B 床', '2号房间 A 床',
  ]);
});

test('床位按房间号合并展示，不出现 A/B 床卡片', () => {
  const cards = [
    ['bed', '1号房间 A 床', 'none'], ['bed', '1号房间 B 床', 'none'],
    ['bed', '2号房间 A 床', 'unverified'], ['sofa', '1号沙发', 'none'],
  ].map(([type, name, association], index): ManagerPositionCard => ({
    id: index + 1, name, type: type as ManagerPositionCard['type'], enabled: true,
    association: association as ManagerPositionCard['association'], statusLabel: '暂无当前选单',
  }));
  assert.deepEqual(groupManagerPositionCards(cards).map(card => card.name), [
    '1号房间', '2号房间', '1号沙发',
  ]);
});

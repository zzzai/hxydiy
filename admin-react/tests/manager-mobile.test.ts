import assert from 'node:assert/strict';
import test from 'node:test';
import { createManagerActionRunner, isMobileManager, managerListParams, managerOrderStatusLabel, managerPrice, managerSelectionActions, managerSourceLabel, readManagerPage } from '../src/technician/managerMobile.ts';

test('unassigned requests both submitted and confirmed with server pagination', () => {
  assert.deepEqual(managerListParams('unassigned', 3), { status: undefined, needs_position_assignment: true, page: 3, page_size: 20 });
  assert.deepEqual(managerListParams('confirmed', 1), { status: 'confirmed', needs_position_assignment: undefined, page: 1, page_size: 20 });
  assert.equal(managerListParams('all', 2).status, undefined);
});
test('price uses only the server payable snapshot, including legitimate zero', () => {
  assert.deepEqual(managerPrice({ status: 'submitted', pricing_snapshot: { payable_total_cents: 9900, applied_price_type: 'group' } }), { label: '预计金额', value: '¥99', priceType: '团购价' });
  assert.equal(managerPrice({ status: 'confirmed', pricing_snapshot: { payable_total_cents: 0, applied_price_type: 'member' } }).value, '¥0');
  for (const value of [undefined, null, -1, '9900', 1.5, NaN, Infinity]) {
    assert.equal(managerPrice({ status: 'submitted', pricing_snapshot: { payable_total_cents: value, applied_price_type: 'member' } }).value, '金额待核实');
  }
  assert.equal(managerPrice({ status: 'confirmed', pricing_snapshot: null }).value, '金额待核实');
});
test('terminal selections never expose confirmation, cancellation or assignment', () => {
  assert.deepEqual(managerSelectionActions({ status: 'confirmed', needs_position_assignment: true }), { confirm: false, cancel: true, assign: true });
  for (const status of ['cancelled', 'expired', 'unknown']) assert.deepEqual(managerSelectionActions({ status, needs_position_assignment: true }), { confirm: false, cancel: false, assign: false });
});
test('manager view refuses technical identity or missing store binding', () => {
  assert.equal(isMobileManager({ role: 'manager', technician_id: null, store_id: 1 }), true);
  for (const staff of [null, { role: 'manager', technician_id: 2, store_id: 1 }, { role: 'technician', technician_id: 2, store_id: 1 }, { role: 'manager', technician_id: null, store_id: 0 }, { role: 'store_manager', technician_id: null, store_id: 1 }]) assert.equal(isMobileManager(staff), false);
});
test('unknown sources never leak internal source codes', () => {
  assert.equal(managerSourceLabel('in_store'), '到店选单');
  assert.equal(managerSourceLabel('personal_qr'), '顾客扫码');
  assert.equal(managerSourceLabel('unrecognized_internal_code'), '其他门店入口');
});
test('a paginated response cannot mix another store into the cards', () => {
  const page = { items: [{ id: 'synthetic-selection', store_id: 1, items: [] }], total: 42, page: 2, page_size: 20 };
  assert.equal(readManagerPage(page, 1).total, 42);
  assert.throws(() => readManagerPage(page, 2));
  assert.throws(() => readManagerPage({ ...page, total: undefined }, 1));
});
test('duplicate actions share one request, and failure allows deliberate retry', async () => {
  const runner = createManagerActionRunner();
  let count = 0;
  let reject!: (reason: Error) => void;
  const request = () => { count++; return new Promise<void>((_resolve, fail) => { reject = fail; }); };
  const first = runner.run('selection:synthetic', request);
  const second = runner.run('selection:synthetic', request);
  assert.equal(first, second);
  await Promise.resolve();
  assert.equal(count, 1);
  reject(new Error('synthetic conflict'));
  await assert.rejects(first);
  await runner.run('selection:synthetic', async () => { count++; });
  assert.equal(count, 2);
});

test('店长只读订单状态不再使用待确认操作文案', () => {
  assert.equal(managerOrderStatusLabel('submitted'), '新订单');
  assert.equal(managerOrderStatusLabel('confirmed'), '已确认');
  assert.equal(managerOrderStatusLabel('cancelled'), '已取消');
  assert.equal(managerOrderStatusLabel('unknown'), '状态待核实');
});

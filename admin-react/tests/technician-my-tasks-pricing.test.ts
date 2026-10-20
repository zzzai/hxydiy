import assert from 'node:assert/strict';
import test from 'node:test';
import { technicianPriceLabel, technicianPricedItemRows, technicianPricingAppliedLabel } from '../src/technician/technicianMobile.ts';

test('我的服务按 pricing.lines 映射逐项会员价和非会员价', () => {
  const rows = technicianPricedItemRows(
    [
      { id: 1, type: 'project', name: '舒享精油 SPA', quantity: 1 },
      { id: 2, type: 'project', name: '草本泡脚', quantity: 2 },
    ],
    {
      store_total_cents: 19900,
      member_total_cents: 15900,
      member_saving_cents: 4000,
      applied_price_type: 'member',
      lines: [
        { line_index: 1, name: '草本泡脚', quantity: 2, store_line_total_cents: 3960, member_line_total_cents: 3160 },
        { line_index: 0, name: '舒享精油 SPA', quantity: 1, store_line_total_cents: 15940, member_line_total_cents: 12740 },
      ],
    },
  );
  assert.deepEqual(rows.map((row) => [row.name, row.quantity, row.member_total_cents, row.store_total_cents]), [
    ['草本泡脚', 2, 3160, 3960],
    ['舒享精油 SPA', 1, 12740, 15940],
  ]);
  assert.equal(rows[0].key === rows[1].key, false);
});

test('我的服务价格行缺少 line 名称时回退到任务项目名与旧字段名', () => {
  const rows = technicianPricedItemRows(
    [{ name: '荷小推', quantity: 1 }],
    {
      lines: [{ line_index: 0, name: '', member_line_price_cents: 8900, store_line_price_cents: 12800 }],
    },
  );
  assert.equal(rows.length, 1);
  assert.equal(rows[0].name, '荷小推');
  assert.equal(rows[0].member_total_cents, 8900);
  assert.equal(rows[0].store_total_cents, 12800);
});

test('无 pricing 时我的服务只回退项目名，不把缺失价格伪造成 0', () => {
  const rows = technicianPricedItemRows(
    [{ name: '舒享精油 SPA', quantity: 1 }, { name: '草本泡脚', quantity: 2 }],
    null,
  );
  assert.deepEqual(rows.map((row) => row.name), ['舒享精油 SPA', '草本泡脚']);
  assert.deepEqual(rows.map((row) => row.member_total_cents), [null, null]);
  assert.deepEqual(rows.map((row) => row.store_total_cents), [null, null]);
  assert.equal(technicianPriceLabel(rows[0].member_total_cents), '—');
  assert.equal(technicianPriceLabel(rows[0].store_total_cents), '—');
});

test('pricing 存在但缺少 lines 时仍回退项目名，合计由页面展示', () => {
  const rows = technicianPricedItemRows(
    [{ name: '草本泡脚', quantity: 1 }],
    { store_total_cents: 7900, member_total_cents: 5900, member_saving_cents: 2000, applied_price_type: 'store', lines: [] },
  );
  assert.deepEqual(rows.map((row) => [row.name, row.member_total_cents, row.store_total_cents]), [['草本泡脚', null, null]]);
  assert.equal(technicianPricingAppliedLabel({ applied_price_type: 'store' }), '本单按非会员价记录');
});

test('我的服务价格行兼容非数字、负数与异常数量', () => {
  const rows = technicianPricedItemRows(
    [{ name: '舒享精油 SPA', quantity: 0 }],
    {
      lines: [
        { line_index: 0, name: '舒享精油 SPA', quantity: 0, member_line_total_cents: -1, store_line_total_cents: 15900 },
      ],
    },
  );
  assert.equal(rows[0].quantity, 1);
  assert.equal(rows[0].member_total_cents, null);
  assert.equal(rows[0].store_total_cents, 15900);
});

test('我的服务本单计价类型覆盖会员、非会员与团购', () => {
  assert.equal(technicianPricingAppliedLabel({ applied_price_type: 'member' }), '本单按会员价记录');
  assert.equal(technicianPricingAppliedLabel({ applied_price_type: 'store' }), '本单按非会员价记录');
  assert.equal(technicianPricingAppliedLabel({ applied_price_type: 'group' }), '本单按团购价记录');
  assert.equal(technicianPricingAppliedLabel({ applied_price_type: null }), '会员价 / 非会员价并列展示');
});

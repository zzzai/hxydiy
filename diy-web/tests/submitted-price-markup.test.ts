import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');

test('提交成功页底部金额沿用按身份解析后的 payableTotal', () => {
  assert.match(appSource, /<strong>\{formatMoney\(payableTotal\)\}<\/strong>/);
  assert.doesNotMatch(appSource, /<strong>\{formatMoney\(Number\(session\.pricing_snapshot\?\.payable_total_cents/);
});

import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

test('会员券包也请求账户优惠券，不再隐藏券入口', () => {
  const source = fs.readFileSync(new URL('../src/components/ProfilePage.tsx', import.meta.url), 'utf8');
  assert.match(source, /getMyCoupons\(token\)/);
  assert.doesNotMatch(source, /isMember \? Promise\.resolve\(\[\] as MyCoupon\[\]\)/);
  assert.match(source, /券包/);
});

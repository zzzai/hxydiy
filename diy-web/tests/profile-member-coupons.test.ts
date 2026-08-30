import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

test('会员个人中心不请求优惠券接口，避免可选接口失败阻断记录加载', () => {
  const source = fs.readFileSync(new URL('../src/components/ProfilePage.tsx', import.meta.url), 'utf8');
  assert.match(source, /isMember \? Promise\.resolve\(\[\] as MyCoupon\[\]\) : getMyCoupons\(token\)/);
  assert.match(source, /loadData\(auth\.token, auth\.user\.is_member\)/);
});

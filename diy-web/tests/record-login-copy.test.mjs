import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('手机号验证码页使用荷小悦草本泡脚登录优惠文案', async () => {
  const source = await readFile(new URL('../src/components/RecordLoginDialog.tsx', import.meta.url), 'utf8');

  assert.match(source, /荷小悦草本泡脚，登录更优惠/);
});

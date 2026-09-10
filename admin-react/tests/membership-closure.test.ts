import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const source = (path: string) => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8');

test('会员管理使用服务端周期命令，不再由前端生成 manual 周期', () => {
  const api = source('api.ts');
  const page = source('pages/UsersPage.tsx');
  assert.match(api, /membership\/enroll/);
  assert.match(api, /membership\/renew/);
  assert.match(api, /membership\/cancel/);
  assert.match(api, /membership\/recover/);
  assert.doesNotMatch(api, /manual-\$\{userId\}/);
  assert.match(page, /支付渠道/);
  assert.match(page, /已向顾客说明并确认会员权益/);
  assert.match(page, /退款处置/);
});

test('电脑后台明确保留动态码核验边界', () => {
  const page = source('pages/UsersPage.tsx');
  assert.match(page, /日常会员核验请使用技师端扫码/);
  assert.match(page, /不能通过手机号直接给予会员价/);
});

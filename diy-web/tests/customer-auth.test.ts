import assert from 'node:assert/strict';
import test from 'node:test';

import {
  authFailureAction,
  isCustomerAuthTokenActive,
  isValidPhone,
  normalizePhone,
  shouldOfferRecordBinding,
} from '../src/customerAuth.ts';

test('手机号输入只保留 11 位数字', () => {
  assert.equal(normalizePhone('138 0013-8000abc'), '13800138000');
});

test('只接受中国大陆手机号格式', () => {
  assert.equal(isValidPhone('13800138000'), true);
  assert.equal(isValidPhone('12800138000'), false);
  assert.equal(isValidPhone('1380013800'), false);
});

test('匿名顾客完成评价后才提示绑定手机号保存服务记录', () => {
  assert.equal(shouldOfferRecordBinding(false, null), false);
  assert.equal(shouldOfferRecordBinding(true, null), true);
  assert.equal(shouldOfferRecordBinding(true, { token: 'x', user: { id: 1, openid: 'h5_x', phone: '13800138000', nickname: '', is_member: false, member_type: null, balance_cents: 0 } }), false);
});

function tokenWithExpiry(exp: number): string {
  const payload = Buffer.from(JSON.stringify({ exp })).toString('base64url');
  return `header.${payload}.signature`;
}

test('本地身份只在登录令牌仍有效时展示为已登录', () => {
  assert.equal(isCustomerAuthTokenActive(tokenWithExpiry(2_000), 1_000), true);
  assert.equal(isCustomerAuthTokenActive(tokenWithExpiry(1_000), 1_000), false);
  assert.equal(isCustomerAuthTokenActive('broken-token', 1_000), false);
});

test('账号接口返回 401 时进入重新验证，不把请先登录当普通错误展示', () => {
  assert.equal(authFailureAction({ status: 401 }), 'reauthenticate');
  assert.equal(authFailureAction({ status: 500 }), 'show-error');
  assert.equal(authFailureAction(new Error('网络异常')), 'show-error');
});

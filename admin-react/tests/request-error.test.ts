import assert from 'node:assert/strict';
import test from 'node:test';
import { requestErrorMessage } from '../src/requestError.ts';
test('network and timeout failures give distinct recovery messages', () => {
  assert.match(requestErrorMessage({ code: 'ERR_NETWORK' }), /检查网络/);
  assert.match(requestErrorMessage({ code: 'ECONNABORTED' }), /暂未确认操作结果/);
});
test('authorization errors retain the store and headquarters boundary in business language', () => {
  assert.match(requestErrorMessage({ response: { status: 403, data: { detail: { code: 'HEADQUARTERS_ADMIN_REQUIRED' } } } }), /仅总部管理员/);
  assert.match(requestErrorMessage({ status: 403, detail: { code: 'STORE_SCOPE_DENIED' } }), /所属门店/);
});
test('validation and server failures never leak payloads or internal exceptions', () => {
  for (const status of [400, 422, 500]) {
    const message = requestErrorMessage({ response: { status, data: { detail: [{ loc: ['body','secret'], input: 'sensitive', msg: 'SQL error' }] } } });
    assert.doesNotMatch(message, /secret|sensitive|SQL|\{|\[/);
  }
});
test('state conflict and expired login are actionable', () => {
  assert.match(requestErrorMessage({ response: { status: 409 } }), /状态已发生变化/);
  assert.match(requestErrorMessage({ response: { status: 401 } }), /重新登录/);
});

test('known validation fields are translated without echoing input or server text', () => {
  const value = requestErrorMessage({ response: { status: 422, data: { detail: [{ loc: ['body', 'name'], type: 'string_too_long', input: 'private value', msg: 'internal debug' }] } } });
  assert.match(value, /名称/);
  assert.doesNotMatch(value, /private|internal|name|body/);
  assert.match(requestErrorMessage({ response: { status: 400, data: { detail: '总部上传必须指定门店' } } }), /所属门店/);
});

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const source = (path: string) => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8');

test('管理端技师 API 覆盖完整账号生命周期且不再调用删除', () => {
  const api = source('api.ts');
  const page = source('pages/TechsPage.tsx');
  for (const path of ['reset-login', 'disable', 'restore', 'resign', 'rehire']) {
    assert.match(api, new RegExp(path));
  }
  assert.doesNotMatch(page, /deleteTechnician/);
  assert.match(page, /login_status/);
  assert.match(page, /仅显示一次/);
});

test('技师账号生命周期写操作携带服务端识别的幂等请求头', () => {
  const api = source('api.ts');
  assert.match(api, /Idempotency-Key/);
  assert.match(api, /lifecycleIdempotencyKey/);
});

test('手机端登录页提供首次激活和重置密码表单', () => {
  const api = source('api.ts');
  const page = source('technician/TechnicianMobileLoginPage.tsx');
  assert.match(api, /technician\/activate/);
  assert.match(page, /首次激活/);
  assert.match(page, /激活凭证/);
  assert.match(page, /确认密码/);
  assert.match(page, /activateTechnician/);
});

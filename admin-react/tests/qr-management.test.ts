import assert from 'node:assert/strict';
import test from 'node:test';

import { servicePositionQrActions } from '../src/servicePositionQr.ts';

test('启用中的二维码可以停用、重新生成和换绑', () => {
  assert.deepEqual(servicePositionQrActions('active', false), ['disable', 'regenerate', 'rebind']);
});

test('已停用但未被替换的二维码可以重新启用或生成新码', () => {
  assert.deepEqual(servicePositionQrActions('disabled', false), ['enable', 'regenerate', 'rebind']);
});

test('已被替换的旧二维码不允许重新启用', () => {
  assert.deepEqual(servicePositionQrActions('disabled', true), []);
});

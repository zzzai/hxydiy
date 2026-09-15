import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildPositionQrPrintDocument,
  getServicePositionQrPermissions,
  servicePositionQrRenderOptions,
  servicePositionQrActions,
} from '../src/servicePositionQr.ts';

test('启用中的二维码可以停用、重新生成和换绑', () => {
  assert.deepEqual(servicePositionQrActions('active', false), ['disable', 'regenerate', 'rebind']);
});

test('已停用但未被替换的二维码可以重新启用或生成新码', () => {
  assert.deepEqual(servicePositionQrActions('disabled', false), ['enable', 'regenerate', 'rebind']);
});

test('已被替换的旧二维码不允许重新启用', () => {
  assert.deepEqual(servicePositionQrActions('disabled', true), []);
});

test('店长可以查看和变更本店服务位二维码', () => {
  assert.deepEqual(getServicePositionQrPermissions('manager'), {
    canView: true,
    canManage: true,
  });
});

test('普通员工只能查看本店服务位二维码，不能变更二维码', () => {
  assert.deepEqual(getServicePositionQrPermissions('staff'), {
    canView: true,
    canManage: false,
  });
});

test('非管理后台角色不能访问服务位二维码操作', () => {
  assert.deepEqual(getServicePositionQrPermissions('technician'), {
    canView: false,
    canManage: false,
  });
});

test('现场打印二维码使用标准静区和中等纠错，避免无 Logo 时码图过密', () => {
  assert.deepEqual(servicePositionQrRenderOptions, {
    width: 1024,
    margin: 4,
    errorCorrectionLevel: 'M',
  });
});

test('批量打印文档保留服务位标识并转义显示文本', () => {
  const html = buildPositionQrPrintDocument([{ code: 'sofa-01', name: '<1号沙发>', image: 'data:image/png;base64,abc' }]);
  assert.match(html, /荷小悦服务位二维码/);
  assert.match(html, /sofa-01/);
  assert.match(html, /&lt;1号沙发&gt;/);
  assert.doesNotMatch(html, /<h1><1号沙发><\/h1>/);
});

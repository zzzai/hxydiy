import assert from 'node:assert/strict';
import test from 'node:test';
import { membershipVerificationView } from '../src/technician/membershipVerification.ts';

test('会员核验先扫码，识别成功后才要求选择本次选单', () => {
  assert.deepEqual(membershipVerificationView(false, 0), {
    showSelection: false,
    primaryAction: '打开摄像头扫码',
  });
  assert.deepEqual(membershipVerificationView(true, 0), {
    showSelection: true,
    primaryAction: '确认绑定本次选单',
  });
});

test('存在冲突服务位时显示核对提示但不阻止扫码', () => {
  assert.deepEqual(membershipVerificationView(false, 1), {
    showSelection: false,
    primaryAction: '打开摄像头扫码',
    blockedMessage: '1 个服务位待店长核对，暂不可绑定会员。',
  });
});

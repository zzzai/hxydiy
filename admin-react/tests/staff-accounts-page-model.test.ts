import assert from 'node:assert/strict';
import test from 'node:test';

import {
  getStaffAccountRoleMeta,
  getStaffAccountStatusMeta,
  staffAccountPayload,
} from '../src/pages/staff-accounts-page-model.ts';

test('员工账号表单创建时提交登录名和初始密码', () => {
  assert.deepEqual(staffAccountPayload({
    username: ' front-desk-01 ', password: ' safe-password-01 ', name: ' 前台员工 ',
    role: 'staff', store_id: 7, status: 'active',
  }, false), {
    username: 'front-desk-01', password: 'safe-password-01', name: '前台员工',
    role: 'staff', store_id: 7, status: 'active',
  });
});

test('员工账号编辑时不回传登录名和空密码', () => {
  assert.deepEqual(staffAccountPayload({
    username: 'immutable-login', password: '   ', name: '新姓名',
    role: 'manager', store_id: 9, status: 'disabled',
  }, true), {
    name: '新姓名', role: 'manager', store_id: 9, status: 'disabled',
  });
});

test('员工账号角色和状态使用运营可读文案', () => {
  assert.deepEqual(getStaffAccountRoleMeta('manager'), { label: '店长', color: 'blue' });
  assert.deepEqual(getStaffAccountStatusMeta('active'), { label: '在职可登录', color: 'green' });
});

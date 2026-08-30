import assert from 'node:assert/strict';
import test from 'node:test';

import {
  customerServiceProgress,
  shouldPollCustomerServiceStatus,
} from '../src/customerServiceStatus.ts';

test('顾客返回项目列表后，已提交的只读服务会话继续轮询状态', () => {
  assert.equal(shouldPollCustomerServiceStatus({
    boot: 'ready',
    hasSession: true,
    hasToken: true,
    readOnly: true,
  }), true);
});

test('普通选购草稿不轮询服务状态', () => {
  assert.equal(shouldPollCustomerServiceStatus({
    boot: 'ready',
    hasSession: true,
    hasToken: true,
    readOnly: false,
  }), false);
});

test('服务中可加选的已确认会话仍继续轮询服务状态', () => {
  assert.equal(shouldPollCustomerServiceStatus({
    boot: 'ready',
    hasSession: true,
    hasToken: true,
    readOnly: false,
    hasSubmittedService: true,
  }), true);
});

test('技师确认服务后，顾客端展示服务中而非旧的提交成功文案', () => {
  assert.deepEqual(customerServiceProgress('in_service'), {
    eyebrow: '服务进行中',
    title: '已开始为您服务',
    message: '技师正在为您服务，如有需要可与现场工作人员沟通。',
    browseLabel: '服务中，可查看本次清单',
  });
});

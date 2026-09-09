import assert from 'node:assert/strict';
import test from 'node:test';

import { createProjectShareUrl, shareProjectLink } from '../src/projectShare.ts';

test('项目分享链接指向可生成微信缩略图的落地页，不泄露服务位或访问凭证', () => {
  const url = new URL(createProjectShareUrl('https://diy.hexiaoyue.com/?store=1&seat=sofa-06&source=store_qr&qr=secret&session=123&token=secret', 'hxy-xiaoqi-90'));
  assert.equal(url.pathname, '/share/project/hxy-xiaoqi-90');
  assert.equal(url.searchParams.get('store'), '1');
  assert.equal(url.searchParams.has('source'), false);
  assert.equal(url.searchParams.has('project'), false);
  assert.equal(url.searchParams.has('seat'), false);
  assert.equal(url.searchParams.has('qr'), false);
  assert.equal(url.searchParams.has('session'), false);
  assert.equal(url.searchParams.has('token'), false);
});

test('系统分享不可用时复制项目链接，取消分享不回退复制', async () => {
  let copied = '';
  const copiedResult = await shareProjectLink({ currentUrl: 'https://diy.hexiaoyue.com/?store=1&seat=sofa-06', projectCode: 'hxy-xiaoqi-90', projectName: '90分钟精油SPA' }, { writeText: async (value) => { copied = value; } });
  assert.equal(copiedResult, 'copied');
  assert.match(copied, /\/share\/project\/hxy-xiaoqi-90/);
  const dismissed = await shareProjectLink({ currentUrl: 'https://diy.hexiaoyue.com/?store=1', projectCode: 'hxy-xiaoqi-90', projectName: '90分钟精油SPA' }, { share: async () => { const error = new Error('cancelled'); error.name = 'AbortError'; throw error; }, writeText: async () => { throw new Error('must not copy'); } });
  assert.equal(dismissed, 'dismissed');
});

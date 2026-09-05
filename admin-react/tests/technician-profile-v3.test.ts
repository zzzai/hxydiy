import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const read = (path: string) => readFileSync(fileURLToPath(new URL(`../${path}`, import.meta.url)), 'utf8');

test('v3 快记默认展示高频项并把扩展维度放在折叠区', () => {
  const source = read('src/technician/TechnicianProfileSheet.tsx');
  assert.match(source, /本次重点/);
  assert.match(source, /更多服务记忆/);
  assert.match(source, /已向顾客复述并确认/);
  assert.match(source, /待保存摘要/);
  assert.match(source, /预算倾向/);
  assert.match(source, /决策关注/);
  assert.equal(source.match(/label="相关情况原话"/g)?.length, 1);
  assert.match(source, /最多选择 2 项/);
  assert.match(source, /最多选择 1 项/);
  assert.doesNotMatch(source, /保存失败，请检查网络后重试/);
});

test('本人历史使用技师专用接口而不是门店级 service-orders', () => {
  assert.match(read('src/api.ts'), /\/technician\/service-history/);
  assert.doesNotMatch(read('src/technician/TechnicianHistoryPage.tsx'), /ServiceOrderList/);
});

test('本人历史明确区分无记录、旧数据未关联和加载失败', () => {
  const source = read('src/technician/TechnicianServiceHistoryPage.tsx');
  assert.match(source, /尚无本人已完成服务/);
  assert.match(source, /旧数据未关联/);
  assert.match(source, /加载失败/);
  assert.match(source, /重试/);
});

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const read = (path: string) => readFileSync(fileURLToPath(new URL(`../${path}`, import.meta.url)), 'utf8');

test('技师快记按服务结果展示对应交接项而不使用折叠区', () => {
  const source = read('src/technician/TechnicianProfileSheet.tsx');
  assert.doesNotMatch(source, /Collapse|更多服务细节/);
  assert.match(source, /已向顾客复述并确认/);
  assert.doesNotMatch(source, /预算倾向|决策关注|Modal/);
  assert.match(source, /name="serviceNote"/);
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

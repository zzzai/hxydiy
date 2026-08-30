import test from 'node:test'; import assert from 'node:assert/strict'; import { readFileSync } from 'node:fs';
const source = readFileSync('src/pages/TodayPage.tsx', 'utf8');
test('TodayPage error retry', () => { assert.match(source, /getTodayStats\(\)/); assert.match(source, /catch/); assert.match(source, /今日运营数据加载失败/); assert.match(source, /重试/); });
test('服务单看板通过资源 provider 加载且不吞掉统一错误', () => { assert.match(source, /dataProvider\.getList/); assert.match(source, /resources\.serviceOrders/); assert.doesNotMatch(source, /getLiveBoard/); assert.doesNotMatch(source, /\.catch\(async/); assert.match(source, /visits/); });
test('今日运营仅提供确认服务和服务结束两个 DIY 服务动作', () => {
  assert.doesNotMatch(source, /startService/);
  assert.doesNotMatch(source, /settleService/);
});

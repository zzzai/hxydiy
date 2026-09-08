import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const source = (path: string) => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8');

test('经营分析只展示服务参考的安全汇总字段', () => {
  const api = source('api.ts');
  const page = source('pages/AnalyticsPage.tsx');

  assert.match(api, /getServiceReferenceSummary/);
  assert.match(page, /服务参考（门店汇总）/);
  assert.match(page, /确认率/);
  assert.match(page, /更正率/);
  assert.doesNotMatch(page, /body_service_notes|service_note|\bquote\b/);
});

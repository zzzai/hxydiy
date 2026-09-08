import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const api = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8');
const page = readFileSync(new URL('../src/pages/AnalyticsPage.tsx', import.meta.url), 'utf8');

test('经营分析通过受限的运营汇总导出接口下载 CSV', () => {
  assert.match(api, /exportOperationsSummary/);
  assert.match(api, /\/admin\/operations-summary\/export/);
  assert.match(api, /responseType: 'blob'/);
  assert.match(page, /exportOperationsSummary/);
  assert.match(page, /导出 CSV/);
  assert.match(page, /URL\.createObjectURL/);
});

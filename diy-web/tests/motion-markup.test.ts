import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const app = fs.readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const sheet = fs.readFileSync(new URL('../src/components/SelectionSummarySheet.tsx', import.meta.url), 'utf8');
const detail = fs.readFileSync(new URL('../src/components/ProjectDetailPage.tsx', import.meta.url), 'utf8');

test('顾客端底部选购栏和详情层声明轻动效标记', () => {
  assert.match(app, /data-motion=["']selection-footer["']/);
  assert.match(detail, /data-motion=["']detail["']/);
});

test('选购清单总价是可播报的并区分待提交语义', () => {
  assert.match(sheet, /本次待提交|已提交服务/);
  assert.match(sheet, /aria-live=["']polite["']/);
  assert.match(sheet, /data-motion=["']selection-sheet["']/);
});

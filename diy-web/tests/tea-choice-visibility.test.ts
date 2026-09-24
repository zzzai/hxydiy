import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');

test('顾客菜单不再展示茶饮选择板块或打开茶饮选择详情', () => {
  assert.doesNotMatch(appSource, /className="catalog-section tea-section"/);
  assert.doesNotMatch(appSource, /<TeaDetailPage\b/);
  assert.doesNotMatch(appSource, /aria-label="选择茶饮"/);
});

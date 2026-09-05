import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

import { projectDetailVisuals } from '../src/projectDetailVisuals.ts';

test('所有已上线项目均提供统一长详情视觉模块', () => {
  const sections = projectDetailVisuals('hxy-xiaoqi-90');

  assert.equal(sections.length, 3);
  assert.match(sections.map((section) => section.title).join(''), /招牌步骤|温热草本/);
  assert.ok(sections.every((section) => section.image.endsWith('.webp')));
  assert.equal(projectDetailVisuals('hxy-xiangxiang-60').length, 3);
  const spa60Sections = projectDetailVisuals('hxy-spa-60');
  assert.equal(spa60Sections.length, 4);
  assert.match(spa60Sections.map((section) => section.title).join(''), /45 分钟精油护理/);
  assert.ok(spa60Sections.every((section) => section.image.includes('hxy-spa-60-detail-')));
  assert.equal(projectDetailVisuals('hxy-spa-90').length, 3);
});

test('详情视觉为每张图提供可读替代文本和顾客说明', () => {
  for (const section of [...projectDetailVisuals('hxy-xiaoqi-90'), ...projectDetailVisuals('hxy-jubu-30')]) {
    assert.ok(section.alt.length >= 8);
    assert.ok(section.body.length >= 12);
    assert.doesNotMatch(`${section.title}${section.body}`, /治疗|治愈|疗效|根治/);
  }
});

test('选购详情页不展示与详情视觉不成套的品牌收尾卡', () => {
  const source = fs.readFileSync(new URL('../src/components/ProjectDetailPage.tsx', import.meta.url), 'utf8');

  assert.doesNotMatch(source, /mini-brand-story/);
  assert.doesNotMatch(source, /把服务做到身边/);
});

test('详情顶部使用项目基础价，底部使用当前项目配置价并保持与整单隔离', () => {
  const source = fs.readFileSync(new URL('../src/components/ProjectDetailPage.tsx', import.meta.url), 'utf8');

  assert.match(source, /const basePrices = detailBasePriceComparison\(project, isMember\)/);
  assert.match(source, /const configuredPrices = detailPriceComparison\(preview, isMember\)/);
  assert.match(source, /<DetailPrice current=\{basePrices\.currentCents\}/);
  assert.match(source, /mini-detail-total[\s\S]*configuredPrices\.currentCents/);
});

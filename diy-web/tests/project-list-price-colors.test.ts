import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

test('项目列表使用克制的绿色普通价和金色会员价区分身份', () => {
  const styles = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');

  assert.match(styles, /--price-regular:\s*#2f6658/i);
  assert.match(styles, /--price-member:\s*#8a6a32/i);
  assert.match(styles, /--price-reference:\s*#66736d/i);
  assert.match(styles, /\.miniapp-catalog-layout \.project-meta strong\s*\{[^}]*color:\s*var\(--price-regular\)/s);
  assert.match(styles, /\.miniapp-catalog-layout \.project-meta \.member-price\s*\{[^}]*color:\s*var\(--price-member\)[^}]*font-weight:\s*600/s);
  assert.match(styles, /\.miniapp-catalog-layout \.project-meta \.member-active strong\s*\{[^}]*color:\s*var\(--price-member\)/s);
  assert.match(styles, /\.miniapp-catalog-layout \.project-meta del\s*\{[^}]*color:\s*var\(--price-reference\)/s);
});

test('项目列表统一插画框并等比铺满不同源图', () => {
  const styles = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');

  assert.match(styles, /\.miniapp-catalog-layout \.mini-project-row\s*\{[^}]*min-height:\s*120px/s);
  assert.match(styles, /\.miniapp-catalog-layout \.project-photo\s*\{[^}]*width:\s*78px[^}]*height:\s*86px[^}]*flex:\s*0 0 78px/s);
  assert.match(styles, /\.miniapp-catalog-layout \.project-photo img\s*\{[^}]*object-fit:\s*cover/s);
  assert.match(styles, /\.miniapp-catalog-layout \.project-photo img\s*\{[^}]*padding:\s*0/s);
});

test('长项目名最多显示两行且顶部推荐卡提供明确的横滑节奏', () => {
  const styles = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');

  assert.match(styles, /\.miniapp-catalog-layout \.project-title-row h3\s*\{[^}]*-webkit-line-clamp:\s*2/s);
  assert.match(styles, /\.miniapp-catalog-layout \.project-title-row h3\s*\{[^}]*white-space:\s*normal/s);
  assert.match(styles, /\.miniapp-promo-strip\s*\{[^}]*scroll-snap-type:\s*x proximity/s);
  assert.match(styles, /\.miniapp-promo\s*\{[^}]*scroll-snap-align:\s*start/s);
});

test('分类导航与项目列表使用紧凑分栏，避免在两者之间留下无意义空白', () => {
  const styles = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');

  assert.match(styles, /\.miniapp-catalog-layout\s*\{[^}]*grid-template-columns:\s*72px minmax\(0, 1fr\)/s);
  assert.match(styles, /\.miniapp-catalog-layout \.catalog-main\s*\{[^}]*padding:\s*0 14px 92px 8px/s);
});

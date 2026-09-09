import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const styles = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');

test('菜单权益区采用方案 A，并保留左侧分类导航', () => {
  assert.match(app, /data-motion=["']promo-strip["']/);
  assert.match(app, /aria-label=["']到店权益["']/);
  assert.match(app, /className=["']category-nav["']/);
  assert.match(styles, /\.miniapp-promo-scroll\s*\{[^}]*scroll-snap-type:\s*x proximity/s);
  assert.match(styles, /\.miniapp-promo\s*\{[^}]*flex:\s*0 0 min\(78vw, 300px\)/s);
});

test('权益区不包含自动轮播或定时切换逻辑', () => {
  assert.doesNotMatch(app, /setInterval\([^\n]*(promo|banner|carousel)/i);
  assert.doesNotMatch(app, /autoPlay|autoplay|carouselIndex/i);
});

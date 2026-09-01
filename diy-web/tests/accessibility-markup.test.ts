import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');

test('服务位切换伪按钮支持键盘 Enter 和 Space', () => {
  assert.match(appSource, /className="miniapp-store"[\s\S]*?onKeyDown=\{\(event\) => \{/);
  assert.match(appSource, /event\.key === 'Enter' \|\| event\.key === ' '/);
});

test('项目卡片具备键盘可操作语义并响应 Enter 和 Space', () => {
  assert.match(appSource, /className=\{`project-card mini-project-row[^`]*`\}[\s\S]*?role="button"[\s\S]*?tabIndex=\{0\}/);
  assert.match(appSource, /onKeyDown=\{\(event\) => \{[\s\S]*?event\.key === 'Enter' \|\| event\.key === ' '/);
});

test('顾客端列表非首屏图片使用 lazy 加载并异步解码', () => {
  assert.match(appSource, /<img src=\{projectImage\(project\)\} alt="" loading="lazy" decoding="async" \/>/);
  assert.match(appSource, /<img src=\{TEA_SERVICE\.image\} alt="" loading="lazy" decoding="async" \/>/);
});

test('局部推拿加购按钮无障碍名称跟随项目名称', () => {
  assert.match(appSource, /aria-label=\{`选择\$\{displayProjectName\(localProject\)\}`\}/);
});

test('详情页选择控件暴露 aria-pressed 状态', () => {
  const detailSource = readFileSync(new URL('../src/components/ProjectDetailPage.tsx', import.meta.url), 'utf8');
  const teaSource = readFileSync(new URL('../src/components/TeaDetailPage.tsx', import.meta.url), 'utf8');
  assert.match(detailSource, /aria-pressed=\{active\}/);
  assert.match(detailSource, /aria-pressed=\{draftChoiceIds\.includes\(choice\.id\)\}/);
  assert.match(teaSource, /aria-pressed=\{active\}/);
});

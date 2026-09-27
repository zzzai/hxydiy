import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { detailMotion, selectionFeedbackMotion, sheetMotion, toastMotion } from '../src/motionPresets.ts';

test('页面动效预设只改变透明度和位移缩放，不动画布局尺寸', () => {
  for (const preset of [detailMotion, selectionFeedbackMotion, sheetMotion, toastMotion]) {
    assert.equal('width' in preset.animate, false);
    assert.equal('height' in preset.animate, false);
    assert.ok('opacity' in preset.animate || 'transform' in preset.animate || 'x' in preset.animate || 'y' in preset.animate || 'scale' in preset.animate);
  }
});

test('动效预设都提供可逆的进入和退出状态', () => {
  for (const preset of [detailMotion, selectionFeedbackMotion, sheetMotion, toastMotion]) {
    assert.ok(preset.initial);
    assert.ok(preset.animate);
    assert.ok(preset.exit);
  }
});

test('详情和选单使用可打断的短时过渡', () => {
  assert.equal(detailMotion.transition.duration, 0.24);
  assert.equal(sheetMotion.transition.duration, 0.24);
  assert.deepEqual(detailMotion.transition.ease, [0.22, 1, 0.36, 1]);
});

test('应用跟随系统减少动效偏好', () => {
  const mainSource = readFileSync(new URL('../src/main.tsx', import.meta.url), 'utf8');
  assert.match(mainSource, /<MotionConfig reducedMotion="user">/);
});

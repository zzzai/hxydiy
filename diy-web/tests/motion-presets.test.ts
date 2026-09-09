import assert from 'node:assert/strict';
import test from 'node:test';

import {
  detailMotion,
  motionForPreference,
  promoStripMotion,
  selectionFeedbackMotion,
  sheetMotion,
  sheetSectionMotion,
  toastMotion,
  valueChangeMotion,
} from '../src/motionPresets.ts';

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

test('新增预设只改变透明度和 transform，并有有限时长', () => {
  for (const preset of [promoStripMotion, valueChangeMotion, sheetSectionMotion(2)]) {
    assert.equal('height' in preset.animate, false);
    assert.equal('width' in preset.animate, false);
    assert.ok('opacity' in preset.animate);
    assert.ok(preset.transition.duration >= 0.15 && preset.transition.duration <= 0.24);
  }
});

test('减少动态效果时移除位移、缩放和错峰', () => {
  const reduced = motionForPreference(sheetSectionMotion(3), true);
  assert.deepEqual(reduced.initial, { opacity: 0 });
  assert.deepEqual(reduced.animate, { opacity: 1 });
  assert.equal(reduced.transition.delay, 0);
});

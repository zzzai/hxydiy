import assert from 'node:assert/strict';
import test from 'node:test';

import { shouldHydrateStoredSelection } from '../src/submittedSelectionRestore.ts';

test('顾客主动返回菜单后，刷新已提交会话不恢复旧选购草稿', () => {
  assert.equal(shouldHydrateStoredSelection({
    draftClearedAfterSubmit: true,
    sessionStatus: 'submitted',
    occupancyStatus: 'waiting_service',
  }), false);
});

test('已提交等待服务时，刷新仍保持空白追加草稿', () => {
  assert.equal(shouldHydrateStoredSelection({
    draftClearedAfterSubmit: true,
    sessionStatus: 'submitted',
    occupancyStatus: 'waiting_service',
  }), false);
});

test('未主动返回菜单的已提交会话仍会恢复清单内容', () => {
  assert.equal(shouldHydrateStoredSelection({
    draftClearedAfterSubmit: false,
    sessionStatus: 'submitted',
    occupancyStatus: 'waiting_service',
  }), true);
});

test('服务中允许加选时不受已清空标记阻断', () => {
  assert.equal(shouldHydrateStoredSelection({
    draftClearedAfterSubmit: true,
    sessionStatus: 'confirmed',
    occupancyStatus: 'in_service',
  }), true);
});

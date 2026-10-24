import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('../src/pages/TodayPage.tsx', import.meta.url), 'utf8');

test('workbench failures remain visible and can be retried without clearing successful sections', () => {
  assert.match(source, /Promise\.allSettled/);
  assert.match(source, /errors\.length > 0 && <Alert/);
  assert.match(source, /action=\{<Button onClick=\{\(\) => void load\(\)\}/);
  assert.match(source, /setWorkbench\([^;]+: null\)/);
  assert.match(source, /setBoard\([^;]+: null\)/);
  assert.match(source, /setReconciliation\([^;]+: null\)/);
  assert.doesNotMatch(source, /\.catch\(async/);
});

test('read-only staff load only the safe selection projection before returning', () => {
  const branch = source.match(/if \(readOnly\) \{([\s\S]+?)\n    \}/)?.[1];
  assert.ok(branch, 'The read-only branch must remain explicit');
  assert.match(branch, /getSelectionSessions\([^;]+, true\)/);
  assert.match(branch, /setErrors\(/);
  assert.match(branch, /return;/);
  assert.doesNotMatch(branch, /getManagerWorkbench|getLiveServicePositionMap|getOrderReconciliation/);
});

test('the overview cannot mutate service or financial state directly', () => {
  assert.doesNotMatch(source, /startService|settleService|markOrderReady|markOrderFinished|assignVisit/);
  assert.doesNotMatch(source, /dataProvider\.(create|update|deleteOne)/);
});

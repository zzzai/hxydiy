import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const styles = fs.readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');

test('评价完成后单一主操作占满容器，不保留空白的第二操作列', () => {
  const completionActions = styles.match(/\.feedback-complete-actions\s*\{([^}]*)\}/)?.[1] || '';

  assert.match(completionActions, /grid-template-columns:\s*1fr/);
  assert.doesNotMatch(completionActions, /grid-template-columns:\s*1fr\s+1fr/);
});

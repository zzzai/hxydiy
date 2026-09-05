import assert from 'node:assert/strict';
import fs from 'node:fs';

const source = fs.readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');
const rule = source.match(/\.project-detail-visuals figure img\s*\{[^}]+\}/)?.[0] ?? '';

assert.match(rule, /height:\s*auto/);
assert.match(rule, /aspect-ratio:\s*auto/);
assert.match(rule, /object-fit:\s*contain/);
assert.doesNotMatch(rule, /aspect-ratio:\s*3\s*\/\s*2/);
assert.doesNotMatch(rule, /object-fit:\s*cover/);

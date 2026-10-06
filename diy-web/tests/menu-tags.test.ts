import assert from 'node:assert/strict';
import test from 'node:test';
import { customerProjectDisplayTagGroups, customerProjectSummaryTags } from '../src/domain.ts';

test('menu badges keep two service features without duplicating duration', () => {
  for (const code of ['hxy-xiangxiang-60', 'hxy-xiaoqi-90', 'hxy-tuina-70', 'hxy-spa-60', 'hxy-spa-90', 'hxy-taoke-60']) {
    const project = { code, name: '', summary: '', category: 'bath', duration_min: 60 };
    const groups = customerProjectDisplayTagGroups(project);
    const labels = [...groups.highlights, ...groups.summary, ...groups.purchase];
    assert(labels.length <= 2);
    assert(labels.every(label => !/\d.*(?:分钟|次\/套)/.test(label)));
  }
});

test('menu filtering does not change the full detail tag mapping', () => {
  const project = { code: 'hxy-xiangxiang-60', name: '', summary: '', category: 'bath', duration_min: 60 };
  assert.deepEqual(customerProjectSummaryTags(project), ['60分钟组合']);
  assert.deepEqual(customerProjectDisplayTagGroups(project).highlights, ['现煮草本', '泡脚按摩']);
});

import assert from 'node:assert/strict';
import test from 'node:test';
import { customerProjectDisplayTagGroups, customerProjectSummaryTags, customerProjectListDescription, customerProjectSummaryText, customerProjectHighlights } from '../src/domain.ts';

test('menu badges preserve service features without duplicating duration or generic rules', () => {
  for (const code of ['hxy-xiangxiang-60', 'hxy-xiaoqi-90', 'hxy-tuina-70', 'hxy-spa-60', 'hxy-spa-90', 'hxy-taoke-60']) {
    const project = { code, name: '', summary: '', category: 'bath', duration_min: 60 };
    const groups = customerProjectDisplayTagGroups(project);
    const labels = [...groups.highlights, ...groups.summary, ...groups.purchase];
    assert.deepEqual(groups.highlights, customerProjectHighlights(project));
    assert(!labels.includes('单次服务'));
    assert(labels.every(label => !/\d.*(?:分钟|次\/套)/.test(label)));
  }
});

test('list descriptions simplify comparison while details retain complete service flows', () => {
  for (const code of ['hxy-xiangxiang-60', 'hxy-xiaoqi-90', 'hxy-nvshen-60']) {
    const project = { code, name: '', summary: '泡脚+按摩（50分钟）+护理', category: 'bath', duration_min: 60 };
    assert.doesNotMatch(customerProjectListDescription(project), /\+|分钟/);
    assert(customerProjectListDescription(project).length <= 20);
    assert.equal(customerProjectSummaryText(project), project.summary);
  }
  const base = { code: 'hxy-qiqing-30', name: '', summary: '', category: 'bath', duration_min: null };
  assert.deepEqual(customerProjectDisplayTagGroups(base).purchase, ['可搭配局部加强']);
  assert.deepEqual(customerProjectDisplayTagGroups(base).summary, []);
  assert.equal(customerProjectListDescription({ ...base, code: 'custom', summary: '清洁+按摩' }), '清洁、按摩');
});

test('menu filtering does not change the full detail tag mapping', () => {
  const project = { code: 'hxy-xiangxiang-60', name: '', summary: '', category: 'bath', duration_min: 60 };
  assert.deepEqual(customerProjectSummaryTags(project), ['60分钟组合']);
  assert.deepEqual(customerProjectDisplayTagGroups(project).highlights, ['现煮草本', '泡脚按摩']);
});

import assert from 'node:assert/strict';
import test from 'node:test';

import { projectFormPayload, projectToForm, supportsDiyOptions } from '../src/projectContent.ts';

test('项目表单把元转换为分并拆分标签', () => {
  const payload = projectFormPayload({ store_price: 39.9, member_price: 29.9, tags_text: '现煮，DIY, 到店确认' });
  assert.deepEqual(payload.prices, { store: 3990, member: 2990 });
  assert.deepEqual(payload.tags, ['现煮', 'DIY', '到店确认']);
});

test('项目数据可还原为编辑表单', () => {
  const form = projectToForm({ tags: ['现煮'], prices: { store: 3990, member: 2990 } });
  assert.equal(form.tags_text, '现煮');
  assert.equal(form.store_price, 39.9);
  assert.equal(form.member_price, 29.9);
});

test('历史 DIY 选项数组回填后仍按数组提交', () => {
  const legacy = [{ label: '力度', note: '适中' }];
  const form = projectToForm({ category: 'bath', diy_options: legacy, prices: {} });
  assert.deepEqual(form.diy_options, legacy);
  assert.deepEqual(projectFormPayload(form).diy_options, legacy);
});

test('固定套盒只保存详情内容并清空 DIY 选项', () => {
  const payload = projectFormPayload({
    category: 'kit',
    detail_modules: [{ title: '固定内容' }],
    diy_options: [{ label: '不应保存' }],
  });

  assert.equal(supportsDiyOptions('kit'), false);
  assert.equal(supportsDiyOptions('bath'), true);
  assert.deepEqual(payload.detail_modules, [{ title: '固定内容' }]);
  assert.deepEqual(payload.diy_options, []);
});

test('历史误分类的套盒编码 hxy-taoke-60 同样清空 DIY 选项', () => {
  const payload = projectFormPayload({
    category: 'balance',
    code: 'hxy-taoke-60',
    detail_modules: [{ title: '固定内容' }],
    diy_options: [{ label: '不应保存' }],
  });

  assert.equal(supportsDiyOptions('balance', 'hxy-taoke-60'), false);
  assert.equal(supportsDiyOptions('balance', 'hxy-tuina-70'), true);
  assert.deepEqual(payload.diy_options, []);
});

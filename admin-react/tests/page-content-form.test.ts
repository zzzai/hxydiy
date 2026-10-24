import assert from 'node:assert/strict';
import test from 'node:test';
import { pageContentPayload, pageContentToForm } from '../src/pageContentForm.ts';
const source = { title: '门店页面', subtitle: '', published: true, promo_banners: [{ eyebrow: '今日推荐', title: '草本泡', project_code: 'keep-me', image_url: '/keep.webp', extension: { retained: true } }], tea_options: [{ name: '茶饮甲', description: '原内容', image_url: '/tea.webp' }, { name: '茶饮乙', note: '乙' }], coupon_prompt: { title: '到店礼', body: '原说明', future_flag: 7 }, brand_story: { title: '品牌', body: '说明', image_url: null } };
test('structured editing round trips all legacy data without mutation', () => {
  assert.deepEqual(pageContentPayload(pageContentToForm(source)), source);
});
test('editing one field preserves nested unknown fields and hidden banner linkage', () => {
  const form = pageContentToForm(source); form.promo_banners[0].title = '新标题'; form.coupon_prompt.body = '新说明';
  const payload = pageContentPayload(form);
  assert.equal(payload.promo_banners[0].project_code, 'keep-me');
  assert.deepEqual(payload.promo_banners[0].extension, { retained: true });
  assert.equal(payload.coupon_prompt.future_flag, 7);
  assert.equal(source.promo_banners[0].title, '草本泡');
  assert.doesNotMatch(JSON.stringify(payload), /_original/);
});
test('removing or reordering a row does not attach another row metadata', () => {
  const form = pageContentToForm(source); form.tea_options.reverse(); form.tea_options.pop();
  assert.deepEqual(pageContentPayload(form).tea_options, [{ name: '茶饮乙', note: '乙' }]);
});
test('unsupported legacy values block editing instead of being silently cleared', () => {
  assert.throws(() => pageContentToForm({ ...source, tea_options: ['not-an-object'] }), /原内容未修改/);
  assert.throws(() => pageContentToForm({ ...source, coupon_prompt: { title: { nested: true } } }), /原内容未修改/);
});
test('disabling publication is explicit and preserves configured content', () => {
  const form = pageContentToForm(source); form.published = false;
  assert.equal(pageContentPayload(form).published, false);
  assert.equal(pageContentPayload(form).promo_banners[0].title, '草本泡');
});

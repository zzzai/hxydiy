import assert from 'node:assert/strict';
import test from 'node:test';
import { createServer } from 'vite';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const formulaCases = [
  { code: 'formula-metal', element: '金', legacy: '清润放松', name: '玉竹百合汤', benefit: '清润舒缓', count: 16, herbs: '桑叶、菊花、芦根、甘草、玉竹、麦冬、百合、薄荷、桔梗、苦杏仁、紫苏叶、桑白皮、枇杷叶、陈皮、艾叶、鱼腥草' },
  { code: 'formula-wood', element: '木', legacy: '舒心解压', name: '玫瑰郁金汤', benefit: '疏肝调气', count: 16, herbs: '白芍、合欢皮、夜交藤、玫瑰花、茯苓、柴胡、香附、郁金、青皮、佛手、远志、枳壳、当归、薄荷、甘草、艾叶' },
  { code: 'formula-water', element: '水', legacy: '温暖养护', name: '杜仲菟丝汤', benefit: '固本护腰', count: 16, herbs: '杜仲、牛膝、桑寄生、艾叶、干姜、续断、狗脊、五加皮、淫羊藿、肉桂、红花、补骨脂、独活、木瓜、花椒、甘草' },
  { code: 'formula-fire', element: '火', legacy: '筋骨轻松', name: '丹参当归汤', benefit: '活络养身', count: 14, herbs: '桂枝、艾叶、当归、川芎、丹参、鸡血藤、红花、苏木、赤芍、泽兰、花椒、干姜、伸筋草、甘草' },
  { code: 'formula-earth', element: '土', legacy: '轻盈畅快', name: '茯苓薏仁汤', benefit: '健脾化湿', count: 15, herbs: '茯苓、薏苡仁、白术、陈皮、藿香、艾叶、泽泻、苍术、白扁豆、赤小豆、砂仁、厚朴、紫苏叶、山楂、甘草' },
];
const formulaReminder = '功效说明为所用药材的常规功效介绍，足浴外用效果仅供参考。';
const representativeHerbs = ['玉竹、百合、麦冬', '玫瑰花、郁金、白芍', '杜仲、牛膝、桑寄生', '丹参、当归、鸡血藤', '茯苓、薏苡仁、白术'];

test('已发布目录保留真实选项 ID，按金木水火土切换完整方剂介绍', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
  try {
    const { default: HerbalFormulaGroup } = await server.ssrLoadModule('/src/components/project-options/HerbalFormulaGroup.tsx');
    const group = { choices: [...formulaCases].reverse().map((formula, index) => ({ id: 201 + index, code: formula.code, name: formula.legacy, description: '旧简介', status: 'active' })) };
    const render = (id: number, readOnly = false) => renderToStaticMarkup(createElement(HerbalFormulaGroup, {
      group, selectedChoiceIds: [id], readOnly, onSelect: () => {},
    }));
    const ordered = render(group.choices.find((choice) => choice.code === 'formula-metal')!.id);
    assert.deepEqual([...ordered.matchAll(/aria-label="([金木水火土]) /g)].map((match) => match[1]), ['金', '木', '水', '火', '土']);
    for (const formula of formulaCases) {
      const choice = group.choices.find((item) => item.code === formula.code)!;
      const markup = render(choice.id);
      assert.match(markup, new RegExp(formula.name));
      assert.match(markup, new RegExp(formula.benefit));
      assert.match(markup, new RegExp(`草本配方 · 共${formula.count}味`));
      assert.match(markup, new RegExp(formula.herbs));
      assert.match(markup, new RegExp(formulaReminder));
      assert.match(markup, new RegExp(`${formula.code}-representatives-20260928.webp`));
      const representatives = representativeHerbs[formulaCases.indexOf(formula)];
      assert.match(markup, new RegExp(`alt="代表药材：${representatives}"`));
      for (const herb of representatives.split('、')) assert.ok(formula.herbs.split('、').includes(herb));
      assert.equal((markup.match(/aria-pressed="true"/g) || []).length, 1);
    }
    assert.equal((render(group.choices[0].id, true).match(/disabled=""/g) || []).length, 5);
    assert.doesNotMatch(ordered, /herbal-formula-art|herbal-formula-caption/);
  } finally { await server.close(); }
});

test('未发布目录沿用旧选择值并共用同一五方展示', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
  try {
    const module = await server.ssrLoadModule('/src/components/project-options/FallbackHerbalFormulaGroup.tsx');
    const render = (selectedName?: string) => renderToStaticMarkup(createElement(module.default, {
      selectedName, readOnly: false, onSelect: () => {},
    }));
    const markup = render();
    for (const formula of formulaCases) assert.match(markup, new RegExp(formula.name));
    assert.match(markup, /玉竹百合汤/);
    assert.match(markup, /草本配方 · 共16味/);
    assert.match(markup, new RegExp(formulaCases[0].herbs));
    assert.equal((markup.match(/aria-pressed="true"/g) || []).length, 1);
    assert.match(render('温暖养护'), /杜仲菟丝汤/);
  } finally { await server.close(); }
});

test('四个草本泡项目在未发布目录时均进入前端五方兜底，足部精修不被误配置', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
  try {
    const { FRONTEND_HERBAL_FORMULA_CODES } = await server.ssrLoadModule('/src/components/ProjectDetailPage.tsx');
    for (const code of ['hxy-qiqing-30', 'hxy-xiangxiang-60', 'hxy-xiaoqi-90', 'hxy-nvshen-60']) assert.equal(FRONTEND_HERBAL_FORMULA_CODES.has(code), true);
    assert.equal(FRONTEND_HERBAL_FORMULA_CODES.has('hxy-foot-refine-1'), false);
  } finally { await server.close(); }
});

test('再放松一会仅展示五个小项且不堆叠项目长简介', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
  try {
    const { default: RelaxProjectGroup } = await server.ssrLoadModule('/src/components/project-options/RelaxProjectGroup.tsx');
    const codes = ['hxy-head-30', 'hxy-caier-30', 'hxy-foot-refine-1', 'hxy-jubu-30', 'hxy-oil-back-30', 'hxy-cupping-scraping-1'];
    const names = ['头疗', '采耳', '足部精修', '局部推拿', '精油开背', '拔罐/刮痧'];
    const projects = codes.map((code, index) => ({
      id: index + 1,
      code,
      name: names[index],
      category: code === 'hxy-jubu-30' ? 'local-strength' : 'small',
      duration_min: 30,
      summary: `${names[index]}的项目长简介，不应该出现在加购卡片中`,
      image_url: '',
      tags: [],
      prices: [{ price_type: 'store', amount_cents: 7900 }, { price_type: 'member', amount_cents: 4900 }],
    }));
    const markup = renderToStaticMarkup(createElement(RelaxProjectGroup, {
      projects,
      catalogChoices: [],
      selectedChoiceIds: [],
      selectedProjectIds: [],
      onToggleChoice: () => {},
      onToggleProject: () => {},
      isMember: false,
    }));
    for (const name of names.filter((name) => name !== '局部推拿')) assert.match(markup, new RegExp(name.replace('/', '\\/')));
    assert.doesNotMatch(markup, /局部推拿/);
    assert.doesNotMatch(markup, /项目长简介/);
    assert.equal((markup.match(/约30分钟/g) || []).length, 5);
    assert.equal((markup.match(/拔罐\/刮痧/g) || []).length, 1);
    assert.doesNotMatch(markup, />拔罐<|>刮痧</);
  } finally { await server.close(); }
});

test('详情价格渲染：匿名与非会员参考价不划线，同价合并，会员保留门店价对比', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
  try {
    const { default: DetailPrice } = await server.ssrLoadModule('/src/components/DetailPrice.tsx');
    const guest = renderToStaticMarkup(createElement(DetailPrice, { current: 7900, comparison: 4900, isMember: false, unit: '每个部位' }));
    assert.match(guest, /会员价 ¥49/);
    assert.doesNotMatch(guest, /<del>/);
    assert.match(guest, /每个部位/);
    assert.match(guest, /<span class="detail-price-primary"><span class="detail-price-label">门店价<\/span><strong>¥79<\/strong><\/span>/, '价格身份必须与对应金额组成不可拆分的阅读单元');
    const member = renderToStaticMarkup(createElement(DetailPrice, { current: 4900, comparison: 7900, isMember: true }));
    assert.match(member, /<del>门店价 ¥79<\/del>/);
    assert.match(member, /<span class="detail-price-label">会员价<\/span><strong>¥49<\/strong>/);
    const same = renderToStaticMarkup(createElement(DetailPrice, { current: 1990, comparison: 1990, isMember: false }));
    assert.equal((same.match(/¥19.9/g) || []).length, 1);
    assert.match(same, /门店价 \/ 会员价/);
    const sameMember = renderToStaticMarkup(createElement(DetailPrice, { current: 1990, comparison: 1990, isMember: true }));
    assert.equal((sameMember.match(/¥19.9/g) || []).length, 1);
    assert.match(sameMember, /门店价 \/ 会员价<\/span><strong>¥19.9<\/strong>/);
  } finally { await server.close(); }
});

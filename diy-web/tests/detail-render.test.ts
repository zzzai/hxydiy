import assert from 'node:assert/strict';
import test from 'node:test';
import { createServer } from 'vite';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

test('草本方详情随选中项切换，保留真实选项标识与只读状态', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
  try {
    const { default: HerbalFormulaGroup } = await server.ssrLoadModule('/src/components/project-options/HerbalFormulaGroup.tsx');
    const group = { choices: [
      { id: 201, code: 'formula-wood', name: '舒心解压', description: '最近有点忙，想松一松\n玫瑰花 · 佛手 · 合欢皮' },
      { id: 205, code: 'formula-water', name: '温暖养护', description: '手脚容易凉，想暖一暖\n杜仲 · 桑寄生 · 淫羊藿' },
    ] };
    const render = (id: number, readOnly = false) => renderToStaticMarkup(createElement(HerbalFormulaGroup, {
      group, selectedChoiceIds: [id], readOnly, onSelect: () => {},
    }));
    assert.match(render(201), /玫瑰花 · 佛手 · 合欢皮/);
    assert.doesNotMatch(render(201), /杜仲 · 桑寄生 · 淫羊藿/);
    assert.match(render(205), /杜仲 · 桑寄生 · 淫羊藿/);
    assert.doesNotMatch(render(205), /玫瑰花 · 佛手 · 合欢皮/);
    assert.equal((render(205).match(/aria-pressed="true"/g) || []).length, 1);
    assert.equal((render(205, true).match(/disabled=""/g) || []).length, 2);
  } finally { await server.close(); }
});

test('未配置后台目录的沐足项目使用前端五方默认值', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
  try {
    const module = await server.ssrLoadModule('/src/components/project-options/FallbackHerbalFormulaGroup.tsx');
    const render = (selectedName?: string) => renderToStaticMarkup(createElement(module.default, {
      selectedName, readOnly: false, onSelect: () => {},
    }));
    const markup = render();
    for (const name of ['舒心解压', '筋骨轻松', '轻盈畅快', '清润放松', '温暖养护']) assert.match(markup, new RegExp(name));
    assert.match(markup, /玫瑰花 · 佛手 · 合欢皮/);
    assert.equal((markup.match(/aria-pressed="true"/g) || []).length, 1);
    assert.match(render('温暖养护'), /杜仲 · 桑寄生 · 淫羊藿/);
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

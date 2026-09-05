import assert from 'node:assert/strict';
import test from 'node:test';
import { createServer } from 'vite';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

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

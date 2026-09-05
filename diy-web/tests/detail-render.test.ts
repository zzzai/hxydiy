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
    const member = renderToStaticMarkup(createElement(DetailPrice, { current: 4900, comparison: 7900, isMember: true }));
    assert.match(member, /<del>门店价 ¥79<\/del>/);
    const same = renderToStaticMarkup(createElement(DetailPrice, { current: 1990, comparison: 1990, isMember: false }));
    assert.equal((same.match(/¥19.9/g) || []).length, 1);
    assert.match(same, /门店价 \/ 会员价/);
  } finally { await server.close(); }
});

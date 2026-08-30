import assert from 'node:assert/strict';
import test from 'node:test';

const baseUrl = process.env.HXY_PRODUCTION_URL || 'https://diy.hexiaoyue.com';

test('生产冒烟：入口、静态资源和健康接口可访问', async () => {
  if (process.env.HXY_PRODUCTION_SMOKE !== '1') {
    test.skip('设置 HXY_PRODUCTION_SMOKE=1 执行线上冒烟');
    return;
  }
  const htmlResponse = await fetch(`${baseUrl}/?store=1&seat=sofa-06`, { cache: 'no-store' });
  assert.equal(htmlResponse.status, 200);
  const html = await htmlResponse.text();
  const script = html.match(/<script[^>]+src="([^"]+\.js)"/i)?.[1];
  assert.ok(script, '入口必须引用前端脚本');
  const scriptResponse = await fetch(new URL(script, baseUrl), { cache: 'no-store' });
  assert.equal(scriptResponse.status, 200);
  assert.ok((await scriptResponse.text()).length > 100_000, '前端脚本不能是空壳');
  const healthResponse = await fetch(`${baseUrl}/api/v1/health`, { cache: 'no-store' });
  assert.equal(healthResponse.status, 200);
  assert.deepEqual(await healthResponse.json(), { status: 'ok', service: 'hxy-customer-api', environment: 'production' });
});

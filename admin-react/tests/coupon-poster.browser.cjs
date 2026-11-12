const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.POSTER_PLAYWRIGHT || '../../output/poster-preview/tools/node_modules/playwright');
const origin = 'http://127.0.0.1:18443';
const output = path.resolve('../output/poster-preview');
const report = { passed: false, cases: [], unexpectedRequests: [], pageErrors: [], productionWrites: 0 };
async function main() {
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'chromium', headless: true, args: ['--no-sandbox', '--disable-background-networking'] });
  const context = await browser.newContext({ viewport: { width: 1080, height: 1600 }, serviceWorkers: 'block', timezoneId: 'Asia/Shanghai', acceptDownloads: true });
  let failAsset = false;
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin || url.pathname.startsWith('/api/')) {
      report.unexpectedRequests.push({ origin: url.origin, path: url.pathname });
      await route.abort(); return;
    }
    if (failAsset && url.pathname.endsWith('ip-paopao-footbath-v3.png')) { await route.fulfill({ status: 503, body: 'Synthetic asset failure' }); return; }
    await route.continue();
  });
  const page = await context.newPage();
  page.on('pageerror', error => report.pageErrors.push(error.message));
  page.setDefaultTimeout(30000);
  try {
    await page.goto(origin + '/preview');
    await page.locator('#poster').waitFor();
    const full = await page.locator('#poster').getAttribute('src');
    await fs.writeFile(path.join(output, 'hxy-coupon-poster-v3.png'), Buffer.from(full.split(',')[1], 'base64'));
    assert.deepEqual(await page.locator('#poster').evaluate(image => [image.naturalWidth, image.naturalHeight]), [972, 1296]);
    report.cases.push('Full poster exported at 972 x 1296 using the isolated single-claim preview link');
    for (const width of [375, 390]) {
      await page.setViewportSize({ width, height: 844 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      await page.screenshot({ path: path.join(output, 'poster-mobile-' + width + '.png'), fullPage: true, animations: 'disabled' });
    }
    report.cases.push('375 and 390 px previews have no horizontal overflow');
    const download = page.waitForEvent('download');
    await page.getByText('保存原图', { exact: true }).click();
    await (await download).saveAs(path.join(output, 'downloaded-poster.png'));
    assert.deepEqual(await fs.readFile(path.join(output, 'downloaded-poster.png')), await fs.readFile(path.join(output, 'hxy-coupon-poster-v3.png')));
    report.cases.push('Downloaded PNG matches the full preview byte for byte');

    failAsset = true;
    await page.goto(origin + '/technician/store');
    await page.getByRole('button', { name: /发券/ }).click();
    await page.getByText('海报生成失败，请重试；领券链接仍可使用', { exact: true }).waitFor();
    assert.equal(await page.evaluate(() => window.posterTest.linkRequests), 1);
    const claimInput = await page.locator('.manager-p0-coupon-share input').inputValue();
    assert.match(claimInput, /store=2&c=synthetic-claim-code/);
    failAsset = false;
    await page.getByRole('button', { name: '重新生成海报', exact: true }).click();
    await page.locator('.manager-coupon-poster-image').waitFor();
    await page.waitForFunction(() => !document.querySelector('.manager-p0-coupon-share .ant-btn-loading'));
    assert.equal(await page.evaluate(() => window.posterTest.linkRequests), 1);
    assert.equal(await page.locator('.manager-p0-coupon-share input').inputValue(), claimInput);
    await page.getByRole('button', { name: '重新生成海报', exact: true }).click();
    await page.locator('.manager-coupon-poster-image').waitFor();
    assert.equal(await page.evaluate(() => window.posterTest.linkRequests), 1);
    assert.equal(await page.evaluate(() => window.posterTest.unexpected), 0);
    await page.screenshot({ path: path.join(output, 'manager-modal-390.png'), fullPage: true, animations: 'disabled' });
    const overflow = await page.evaluate(() => ({ viewport: innerWidth, width: document.documentElement.scrollWidth, elements: [...document.querySelectorAll('body *')].filter(el => { const r = el.getBoundingClientRect(); return r.width > 0 && (r.right > innerWidth + 1 || r.left < -1); }).map(el => ({ tag: el.tagName, cls: el.className, width: el.getBoundingClientRect().width })).slice(0, 18) }));
    assert.equal(overflow.width <= overflow.viewport, true, JSON.stringify(overflow));
    report.cases.push('Actual manager modal recovers from image failure without creating another coupon link');
    report.cases.push('Repeated image regeneration preserves the original store and claim URL');
    assert.deepEqual(report.pageErrors, []);
    assert.deepEqual(report.unexpectedRequests, []);
    report.passed = true;
  } catch (error) {
    await page.screenshot({ path: path.join(output, 'failure.png'), fullPage: true, animations: 'disabled' });
    await fs.writeFile(path.join(output, 'failure-dom.txt'), await page.locator('body').innerText());
    throw error;
  } finally {
    await fs.writeFile(path.join(output, 'browser-report.json'), JSON.stringify(report, null, 2));
    await browser.close();
    console.log(JSON.stringify(report));
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });

// Real local component rendering; synthetic identity and seat, no production writes.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const fixture = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const reference = process.argv[3];
assert.equal(fixture.synthetic, true);
assert.equal(new URL(fixture.apiBase).hostname, '127.0.0.1');
const out = path.resolve(process.argv[4] || 'output/playwright/customer-service-account-sheet-02');
fs.mkdirSync(out, { recursive: true });
(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  const checks = [];
  try {
    for (const [width, height] of [[375, 844], [390, 844], [375, 568], [390, 568]]) {
      const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1 });
      await context.addInitScript(auth => {
        localStorage.setItem('hxy_diy_customer_auth', JSON.stringify(auth));
        Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async text => { if (window.failCopy) throw new Error('Synthetic clipboard denial'); window.copiedName = text; } } });
      }, fixture.accounts.full);
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(fixture.url);
      await page.locator('.return-entry-banner').waitFor();
      await page.locator('.toast').waitFor({ state: 'hidden' });
      await page.locator('.return-entry-banner button').filter({ hasText: '查看入口' }).click();
      await page.locator('.service-account-qr').waitFor();
      await page.getByRole('heading', { name: '下次来，不用找沙发码', exact: true }).waitFor();
      await page.locator('.service-account-qr').evaluate(img => img.decode());
      const fontClient = await context.newCDPSession(page);
      await fontClient.send('DOM.enable');
      await fontClient.send('CSS.enable');
      const fontDocument = await fontClient.send('DOM.getDocument');
      const fontNode = await fontClient.send('DOM.querySelector', { nodeId: fontDocument.root.nodeId, selector: '.service-account-next' });
      const platformFonts = await fontClient.send('CSS.getPlatformFontsForNode', { nodeId: fontNode.nodeId });
      assert(platformFonts.fonts.some(font => /YaHei|PingFang|Noto Sans/.test(font.familyName)));
      await fontClient.detach();
      assert.equal(await page.locator('.return-link-field').count(), 0);
      assert.equal(await page.getByRole('button', { name: '复制备用链接' }).count(), 0);
      const dimensions = await page.locator('.service-account-qr').evaluate(img => {
        const box = img.getBoundingClientRect();
        return { width: box.width, height: box.height, top: box.top, bottom: box.bottom, select: getComputedStyle(img).userSelect, handler: img.oncontextmenu === null, natural: img.naturalWidth };
      });
      assert.equal(dimensions.width, dimensions.height);
      assert(dimensions.natural === 258 && dimensions.select === 'auto' && dimensions.handler);
      assert(dimensions.top >= 0 && dimensions.bottom <= height);
      const closeBox = await page.getByRole('button', { name: '关闭入口提示' }).boundingBox();
      assert(closeBox.y >= 0 && closeBox.y + closeBox.height <= height);
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.screenshot({ path: path.join(out, `${width}x${height}-home-sheet.png`) });
      await page.getByRole('button', { name: '复制名称' }).click();
      assert.equal(await page.evaluate(() => window.copiedName), '荷小悦草本轻养');
      await page.getByText('名称已复制，可到微信搜索。', { exact: true }).waitFor();
      await page.evaluate(() => { window.failCopy = true; });
      await page.getByRole('button', { name: '复制名称' }).click();
      await page.getByText('无法自动复制，可在微信搜索「荷小悦草本轻养」。', { exact: true }).waitFor();
      await page.screenshot({ path: path.join(out, `${width}x${height}-copy-failure.png`) });
      await page.getByRole('button', { name: '关闭入口提示' }).click();
      assert.equal(await page.locator('.service-account-sheet').count(), 0);
      await page.goto('http://127.0.0.1:4185/?store=1&view=return');
      await page.locator('.return-save-card button').click();
      await page.locator('.service-account-sheet').waitFor();
      await page.locator('.service-account-qr').evaluate(img => img.decode());
      await page.screenshot({ path: path.join(out, `${width}x${height}-my-sheet.png`) });
      await page.getByRole('button', { name: '关闭入口提示' }).press('Escape');
      assert.equal(await page.locator('.service-account-sheet').count(), 0);
      await page.locator('.return-contact-card button').click();
      await page.getByRole('heading', { name: '周二会员福利' }).waitFor();
      assert.equal(await page.locator('.store-contact-qr').count(), 1);
      assert.equal(await page.locator('.service-account-qr').count(), 0);
      assert.equal(errors.length, 0);
      checks.push({ width, height, homeAndMy: true, copySuccessAndFailure: true, qr: dimensions, closeAndEscape: true, wecomUnchanged: true, platformFonts: platformFonts.fonts, consoleErrors: errors });
      await context.close();
    }
    const qr = path.resolve('public/assets/hxy-service-account-qr.jpg');
    const payload = execFileSync('python', ['-c', 'import cv2,sys; print(cv2.QRCodeDetector().detectAndDecode(cv2.imread(sys.argv[1]))[0])', qr], { encoding: 'utf8' }).trim();
    assert.equal(payload, 'http://weixin.qq.com/r/mp/jCebg3DEEi1trTTg93Ke');
    if (reference) {
      const comparison = await browser.newPage({ viewport: { width: 780, height: 844 } });
      const source = fs.readFileSync(reference).toString('base64');
      const implementation = fs.readFileSync(path.join(out, '390x844-my-sheet.png')).toString('base64');
      await comparison.setContent(`<style>body{margin:0;display:flex}img{display:block;width:390px;height:844px;object-fit:contain}</style><img src="data:image/png;base64,${source}"><img src="data:image/png;base64,${implementation}">`);
      await comparison.screenshot({ path: path.join(out, 'reference-vs-implementation.png') });
    }
    fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify({ productionWrites: false, synthetic: true, qrPayloadVerified: true, checks }, null, 2));
    console.log(JSON.stringify({ passed: checks.length, report: path.join(out, 'result.json') }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

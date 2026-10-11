// Production frontend build; local request stubs and public catalog snapshots only.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.SEAT_ENTRY_UI_URL || 'http://127.0.0.1:4190';
assert(['127.0.0.1', 'localhost'].includes(new URL(base).hostname));
const out = path.resolve('output/playwright/customer-seat-ui-release');
fs.mkdirSync(out, { recursive: true });

(async () => {
  const snapshots = {};
  for (const url of ['/projects?store_id=1', '/addons?store_id=1', '/stores/1/service-position-map', '/stores/1/page-content']) {
    const response = await fetch(`https://diy.hexiaoyue.com/api/v1${url}`);
    assert(response.ok);
    snapshots[url.split('?')[0]] = await response.json();
  }
  const map = snapshots['/stores/1/service-position-map'];
  // Keep the public labels/order; never expose occupancy records to local artifacts.
  map.positions = map.positions.map(item => ({ ...item, occupancy: null }));
  const sofas = map.positions.filter(item => item.type === 'sofa').sort((a, b) => a.sort_order - b.sort_order);
  const expected = { left: sofas.filter((_, index) => index % 2 === 0).map(item => item.customer_label), right: sofas.filter((_, index) => index % 2 === 1).map(item => item.customer_label) };
  const browser = await chromium.launch({ channel: 'chrome' });
  const results = [];
  try {
    for (const [width, height] of [[375, 844], [390, 844], [375, 568], [390, 568]]) {
      const context = await browser.newContext({ viewport: { width, height } });
      const writes = [], external = [], errors = [], consoleErrors = [];
      let entryPosition = null;
      let draft = { id: 'ui-test-session', store_id: 1, source: 'store_qr', device_label: 'UI test', status: 'draft', items: [], pricing_snapshot: {}, store_total_cents: 0, member_total_cents: 0, expires_at: null, submitted_at: null, cart_version: 1 };
      await context.route('**/*', async route => {
        const request = route.request();
        const url = new URL(request.url());
        if (url.origin !== new URL(base).origin) { external.push(url.origin); return route.abort(); }
        if (!url.pathname.startsWith('/api/v1/')) return route.continue();
        const key = url.pathname.slice('/api/v1'.length);
        if (request.method() !== 'GET') writes.push(key);
        if (key in snapshots) return route.fulfill({ json: snapshots[key] });
        if (key === '/coupons/templates') return route.fulfill({ json: { items: [] } });
        if (key === '/events') return route.fulfill({ json: { accepted: true } });
        if (key === '/entry-sessions') {
          entryPosition = sofas.find(item => item.code === request.postDataJSON().position_code);
          assert(entryPosition);
          return route.fulfill({ json: { session: draft, position: entryPosition, occupancy: { id: 1, store_id: 1, room_id: entryPosition.id, selection_session_id: draft.id, active_room_id: null, status: 'held', source: 'store_qr', hold_expires_at: null, version: 1 }, access_token: 'ui-test-access', collaboration_token: 'ui-test-collaborator', collaboration_mode: 'shared_draft', cart_version: 1, resumed: false, returning_browser: false } });
        }
        if (key === '/selection-sessions/ui-test-session/service-status') return route.fulfill({ json: { selection_session_id: draft.id, occupancy_status: 'held', can_evaluate: false, evaluated: false } });
        if (key === '/selection-sessions/ui-test-session' && request.method() === 'PATCH') draft = { ...draft, items: request.postDataJSON().items, cart_version: draft.cart_version + 1 };
        if (key === '/selection-sessions/ui-test-session') return route.fulfill({ json: draft });
        if (key === '/selection-sessions/ui-test-session/quote') return route.fulfill({ json: { items: request.postDataJSON().items, pricing: {}, saving_hint: null } });
        throw new Error(`Unexpected API request: ${request.method()} ${key}`);
      });
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
      await page.goto(`${base}/?store=1&view=menu`);
      await page.getByRole('heading', { name: '到店选项目', exact: true }).waitFor();
      await page.locator('.initial-seat').last().waitFor();
      await page.evaluate(() => document.fonts.ready);
      assert.deepEqual(await page.locator('.initial-seat-column').first().locator('strong').allTextContents(), expected.left);
      assert.deepEqual(await page.locator('.initial-seat-column').last().locator('strong').allTextContents(), expected.right);
      assert.equal(await page.getByText('交互预览 · 演示数据', { exact: true }).count(), 0);
      const metrics = await page.evaluate(() => {
        const style = selector => { const s = getComputedStyle(document.querySelector(selector)); return { size: s.fontSize, weight: s.fontWeight }; };
        const image = document.querySelector('.seat-entry-brand img');
        return { title: style('.entry-panel h1'), report: style('.seat-report-card h2'), description: style('.seat-report-card p'), padding: getComputedStyle(document.querySelector('.seat-entry-page')).paddingLeft, ip: { width: image.width, height: image.height, fit: getComputedStyle(image).objectFit, loaded: image.complete && image.naturalWidth > 0 }, overflow: document.documentElement.scrollWidth > innerWidth };
      });
      assert.deepEqual(metrics.title, { size: '21px', weight: '600' });
      assert.deepEqual(metrics.report, { size: '17px', weight: '600' });
      assert.equal(metrics.description.size, '14px');
      assert.equal(metrics.padding, '22px');
      assert.deepEqual(metrics.ip, { width: 80, height: 84, fit: 'contain', loaded: true });
      assert.equal(metrics.overflow, false);
      const button = page.getByRole('button', { name: '查看我的检测报告', exact: true });
      const box = await button.boundingBox();
      assert(box.y >= 0 && box.y + box.height <= height);
      await page.screenshot({ path: path.join(out, `${width}x${height}-entry.png`) });
      await page.evaluate(() => scrollTo(0, document.documentElement.scrollHeight));
      const last = await page.locator('.initial-seat').last().boundingBox();
      assert(last.y >= 0 && last.y + last.height <= height);
      await page.screenshot({ path: path.join(out, `${width}x${height}-last-row.png`) });
      await button.click();
      await page.getByPlaceholder('请输入手机号').waitFor();
      assert.equal(await page.getByText(/演示手机号/).count(), 0);
      assert(!writes.some(key => /entry-sessions|selection-sessions|occupancies|auth/.test(key)));
      await page.screenshot({ path: path.join(out, `${width}x${height}-anonymous-report-login.png`) });
      await page.goBack();
      await page.locator('.profile-page').waitFor({ state: 'hidden' });
      await page.getByRole('heading', { name: '到店选项目', exact: true }).waitFor();
      let menu = false;
      if (height === 844) {
        // Test only the normal menu using a synthetic entry response, never a production POST.
        const selectable = page.locator('.initial-seat:not([aria-disabled="true"])').first();
        await selectable.click();
        await page.locator('.customer-app').waitFor();
        assert.equal(await page.locator('.miniapp-store em').textContent(), entryPosition.customer_label);
        const categories = page.locator('.category-nav button');
        assert.equal(await categories.count(), 5);
        assert.deepEqual(await categories.evaluateAll(items => items.map(item => item.dataset.categoryId)), ['bath', 'balance', 'care', 'small', 'kit']);
        await page.locator('[data-category-id="bath"]').click();
        const plus = page.locator('#section-bath .luckin-add').first();
        await plus.click();
        await page.locator('.project-detail-page').waitFor();
        await page.screenshot({ path: path.join(out, `${width}x${height}-detail.png`) });
        await page.goBack();
        await page.locator('.project-detail-page').waitFor({ state: 'hidden' });
        await page.locator('[data-category-id="balance"]').click();
        assert.equal(await page.locator('[data-category-id="balance"]').getAttribute('aria-current'), 'true');
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await page.screenshot({ path: path.join(out, `${width}x${height}-menu.png`) });
        menu = true;
      }
      assert.deepEqual(external, []);
      assert.deepEqual(errors, []);
      assert.deepEqual(consoleErrors, []);
      results.push({ width, height, metrics, order: expected, lastRowClear: true, reportLoginWithoutSeat: true, noProductionWrites: true, menuRegression: menu, external, errors, consoleErrors });
      await context.close();
    }
    fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify({ environment: 'production build, local stubs + read-only public catalog snapshot', productionWrites: false, results }, null, 2));
    console.log(JSON.stringify({ passed: results.length, menuCases: 2, productionWrites: false, errors: 0, report: path.join(out, 'result.json') }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });

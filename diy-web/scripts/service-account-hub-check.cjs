// Real production frontend; public snapshots and local transport fixtures only.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.SERVICE_HUB_UI_URL || 'http://127.0.0.1:4191';
assert(['127.0.0.1', 'localhost'].includes(new URL(base).hostname));
const out = path.resolve('output/playwright/customer-service-account-hub');
fs.mkdirSync(out, { recursive: true });

(async () => {
  const snapshots = {};
  for (const key of ['/projects?store_id=1', '/addons?store_id=1', '/stores/1/service-position-map', '/stores/1/page-content']) {
    const response = await fetch(`https://diy.hexiaoyue.com/api/v1${key}`);
    assert(response.ok);
    snapshots[key.split('?')[0]] = await response.json();
  }
  const map = snapshots['/stores/1/service-position-map'];
  map.positions = map.positions.map(item => ({ ...item, occupancy: null }));
  const sofas = map.positions.filter(item => item.type === 'sofa').sort((a, b) => a.sort_order - b.sort_order);
  const browser = await chromium.launch({ channel: 'chrome' });
  const results = [];
  try {
    for (const [width, height] of [[375, 844], [390, 844], [375, 568], [390, 568]]) {
      const context = await browser.newContext({ viewport: { width, height } });
      const calls = [], errors = [];
      let chosen = null;
      const draft = { id: 'hub-test-session', store_id: 1, source: 'store_qr', status: 'draft', items: [], pricing_snapshot: {}, store_total_cents: 0, member_total_cents: 0, expires_at: null, submitted_at: null, cart_version: 1 };
      const occupancy = { id: 1, store_id: 1, room_id: sofas[0].id, selection_session_id: draft.id, status: 'held', source: 'store_qr', hold_expires_at: null, version: 1 };
      await context.addInitScript(() => {
        // Old visit records must remain unused, not be deleted or restored.
        localStorage.setItem('hxy_diy_entry_1_sofa-03', JSON.stringify({ positionCode: 'sofa-03', accessToken: 'stale-secret', session: { id: 'stale-session', status: 'submitted' } }));
      });
      await context.route('**/*', async route => {
        const request = route.request(), url = new URL(request.url());
        if (url.origin !== new URL(base).origin) return route.abort();
        if (!url.pathname.startsWith('/api/v1/')) return route.continue();
        const key = url.pathname.slice(7);
        calls.push({ method: request.method(), key });
        if (key === '/stores/1/service-position-map' && url.searchParams.get('session_id')) return route.fulfill({ json: { ...map, positions: map.positions.map(item => item.code === chosen.code ? { ...item, is_current: true, occupancy: { ...occupancy, room_id: chosen.id } } : item) } });
        if (key in snapshots) return route.fulfill({ json: snapshots[key] });
        if (key === '/coupons/templates') return route.fulfill({ json: { items: [] } });
        if (key === '/events') return route.fulfill({ json: { accepted: true } });
        if (key === '/entry-sessions') {
          const input = request.postDataJSON();
          chosen = sofas.find(item => item.code === input.position_code);
          assert(chosen);
          assert.equal(input.source, input.entry_token ? 'personal_qr' : 'store_qr');
          return route.fulfill({ json: { session: draft, position: chosen, occupancy: { ...occupancy, room_id: chosen.id }, access_token: 'hub-test-access', collaboration_token: 'hub-test-collaborator', collaboration_mode: 'shared_draft', cart_version: 1, resumed: false } });
        }
        if (key === '/selection-sessions/hub-test-session') return route.fulfill({ json: draft });
        if (key === '/selection-sessions/hub-test-session/service-status') return route.fulfill({ json: { selection_session_id: draft.id, occupancy_status: 'held', can_evaluate: false, evaluated: false } });
        errors.push(`Unexpected API: ${request.method()} ${key}`);
        return route.fulfill({ status: 500, json: { detail: 'Unexpected fixture request' } });
      });
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
      const assertNoVisit = () => assert(!calls.some(item => /entry-sessions|selection-sessions|occupancies|service-position-map|health|auth/.test(item.key)), JSON.stringify(calls));
      for (const source of ['', '&source=service_account', '&source=store_qr']) {
        await page.goto(`${base}/?store=1&view=menu${source}`);
        await page.getByRole('button', { name: /查看检测报告/ }).waitFor();
        assert.equal(await page.locator('.initial-seat').count(), 0);
        assertNoVisit();
      }
      const metrics = await page.evaluate(() => {
        const image = document.querySelector('.seat-entry-brand img');
        return { padding: getComputedStyle(document.querySelector('.service-hub-page')).paddingLeft, title: getComputedStyle(document.querySelector('h1')).fontSize, card: getComputedStyle(document.querySelector('.service-hub-entry strong')).fontSize, description: getComputedStyle(document.querySelector('.service-hub-entry small')).fontSize, ip: { width: image.width, height: image.height, fit: getComputedStyle(image).objectFit }, overflow: document.documentElement.scrollWidth > innerWidth };
      });
      assert.deepEqual(metrics, { padding: '22px', title: '21px', card: '17px', description: '14px', ip: { width: 80, height: 84, fit: 'contain' }, overflow: false });
      await page.screenshot({ path: path.join(out, `${width}x${height}-hub.png`) });
      await page.getByRole('button', { name: /查看检测报告/ }).click();
      await page.getByPlaceholder('请输入手机号').waitFor();
      assertNoVisit();
      await page.screenshot({ path: path.join(out, `${width}x${height}-report-login.png`) });
      await page.getByRole('button', { name: '返回首页', exact: true }).click();
      await page.locator('.profile-page').waitFor({ state: 'hidden' });
      await page.getByRole('link', { name: /进入菜单/ }).click();
      await page.locator('.customer-app').waitFor();
      assertNoVisit();
      assert.equal(await page.locator('.shared-cart-banner,.submitted-browse-banner,.selection-footer').count(), 0);
      assert.deepEqual(await page.locator('.category-nav button').evaluateAll(items => items.map(item => item.dataset.categoryId)), ['bath', 'balance', 'care', 'small', 'kit']);
      await page.reload();
      await page.locator('.customer-app').waitFor();
      assertNoVisit();
      for (const id of ['balance', 'care', 'small', 'kit', 'bath']) {
        await page.locator(`[data-category-id="${id}"]`).click();
        assert.equal(await page.locator(`[data-category-id="${id}"]`).getAttribute('aria-current'), 'true');
      }
      await page.screenshot({ path: path.join(out, `${width}x${height}-menu.png`) });
      await page.locator('#section-bath .luckin-add').first().click();
      await page.locator('.project-detail-page').waitFor();
      assert.equal(await page.locator('.mini-seat-reminder').count(), 0);
      assert.equal(await page.getByRole('button', { name: '已提交前台', exact: true }).count(), 0);
      assert(await page.getByRole('button', { name: '到店选项目', exact: true }).isEnabled());
      await page.screenshot({ path: path.join(out, `${width}x${height}-detail.png`) });
      await page.getByRole('button', { name: '返回项目列表', exact: true }).click();
      await page.locator('.project-detail-page').waitFor({ state: 'hidden' });
      assertNoVisit();
      await page.getByRole('link', { name: '首页', exact: true }).click();
      await page.getByRole('link', { name: /进入菜单/ }).waitFor();
      assertNoVisit();
      await page.getByRole('link', { name: /进入菜单/ }).click();
      await page.getByRole('link', { name: '到店选项目', exact: true }).click();
      await page.locator('.initial-seat').last().waitFor();
      assert(!calls.some(item => item.method !== 'GET' && item.key !== '/events'));
      assert.deepEqual(await page.locator('.initial-seat-column').first().locator('strong').allTextContents(), sofas.filter((_, index) => index % 2 === 0).map(item => item.customer_label));
      await page.locator('.initial-seat:not([aria-disabled="true"])').first().click();
      await page.locator('.customer-app').waitFor();
      assert.equal(await page.locator('.miniapp-store em').textContent(), chosen.customer_label);
      assert.equal(calls.filter(item => item.key === '/entry-sessions').length, 1);
      assert.equal(await page.locator('.selection-footer').count(), 0);
      await page.locator('#section-bath .luckin-add').first().click();
      await page.locator('.project-detail-page').waitFor();
      assert.equal(await page.getByRole('button', { name: '到店选项目', exact: true }).count(), 0);
      assert(await page.getByRole('button', { name: '加入本次服务', exact: true }).isEnabled());
      assert.equal(await page.locator('.mini-seat-reminder strong').textContent(), chosen.customer_label);
      if (height === 844) {
        await page.goto(`${base}/?store=1&view=menu&seat=${sofas[1].code}&qr=local-signed-qr`);
        await page.locator('.customer-app').waitFor();
        assert.equal(await page.locator('.miniapp-store em').textContent(), sofas[1].customer_label);
        assert.equal(await page.locator('.service-hub-page').count(), 0);
        const entryCalls = calls.filter(item => item.key === '/entry-sessions').length;
        await page.goto(`${base}/?store=1&view=menu&session=hub-test-session&token=hub-test-access`);
        await page.locator('.customer-app').waitFor();
        assert.equal(await page.locator('.miniapp-store em').textContent(), sofas[1].customer_label);
        assert.equal(calls.filter(item => item.key === '/entry-sessions').length, entryCalls);
        assert.equal(new URL(page.url()).searchParams.get('seat'), sofas[1].code);
      }
      assert.deepEqual(errors, []);
      results.push({ width, height, metrics, hubSources: 3, anonymousReportReturn: true, unseatedReload: true, oldRecordUnused: true, categories: 5, detailReturn: true, explicitSeatOnly: true, signedQrAndBoundDevice: height === 844, errors });
      await context.close();
    }
    fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify({ environment: 'production frontend build; public catalog + local transport fixtures', productionWrites: false, results }, null, 2));
    console.log(JSON.stringify({ passed: results.length, productionWrites: false, report: path.join(out, 'result.json') }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });

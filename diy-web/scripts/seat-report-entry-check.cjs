// Real component navigation with isolated API identities; no production writes.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const fixture = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
assert.equal(fixture.synthetic, true);
assert.equal(new URL(fixture.apiBase).hostname, '127.0.0.1');
const out = path.resolve('output/playwright/customer-seat-report-entry');
fs.mkdirSync(out, { recursive: true });
const root = 'http://127.0.0.1:4185/?store=1&view=menu&source=service_account';
const headers = { Authorization: `Bearer ${fixture.accounts.full.token}` };
(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  const results = [];
  try {
    const reset = await fetch(`${fixture.apiBase}/synthetic-test/control`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ account: 'full', action: 'reset' }) });
    assert(reset.ok);
    const consent = await (await fetch(`${fixture.apiBase}/api/v1/me/tcm-report-consent`, { headers })).json();
    const grant = await fetch(`${fixture.apiBase}/api/v1/me/tcm-report-consent`, { method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify({ accepted: true, version: consent.version }) });
    assert(grant.ok);
    const publicMap = await (await fetch(`${fixture.apiBase}/api/v1/stores/1/service-position-map`)).json();
    const sample = publicMap.positions[0];
    // Eight synthetic positions exercise the existing alternating layout, not new production data.
    const map = { ...publicMap, positions: [1, 6, 2, 7, 3, 8, 5, 9].map((label, index) => ({ ...sample, id: 100 + index, code: `synthetic-seat-${label}`, customer_label: `${label}号沙发`, sort_order: index })) };
    for (const [width, height] of [[375, 844], [390, 844], [375, 568], [390, 568]]) {
      for (const loggedIn of [false, true]) {
        const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1 });
        if (loggedIn) await context.addInitScript(auth => localStorage.setItem('hxy_diy_customer_auth', JSON.stringify(auth)), fixture.accounts.full);
        await context.route('**/api/v1/stores/1/service-position-map', route => route.fulfill({ json: map }));
        const page = await context.newPage();
        const errors = [];
        const requests = [];
        page.on('pageerror', error => errors.push(error.message));
        page.on('request', request => requests.push({ path: new URL(request.url()).pathname, method: request.method() }));
        await page.goto(root);
        await page.getByRole('heading', { name: '选择您所在的沙发' }).waitFor();
        const button = page.getByRole('button', { name: '查看我的检测报告', exact: true });
        const box = await button.boundingBox();
        assert(box.y >= 0 && box.y + box.height <= height);
        assert.equal(await page.locator('.initial-seat').count(), 8);
        assert.deepEqual(await page.locator('.initial-seat-column').first().locator('strong').allTextContents(), ['1号沙发', '2号沙发', '3号沙发', '5号沙发']);
        assert.deepEqual(await page.locator('.initial-seat-column').last().locator('strong').allTextContents(), ['6号沙发', '7号沙发', '8号沙发', '9号沙发']);
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await page.screenshot({ path: path.join(out, `${width}x${height}-seat.png`) });
        await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
        const lastSeat = await page.locator('.initial-seat').last().boundingBox();
        const footer = await page.locator('.seat-report-entry').boundingBox();
        assert(lastSeat.y + lastSeat.height <= footer.y);
        await page.screenshot({ path: path.join(out, `${width}x${height}-last-row.png`) });
        await button.click();
        await page.locator('.profile-report-view').waitFor();
        if (loggedIn) {
          await page.locator('.my-reports-list').waitFor();
          assert.equal(await page.locator('.my-reports-consent').count(), 0);
        } else {
          await page.getByPlaceholder('请输入手机号').waitFor();
          await page.locator('.profile-login-submit').click();
          await page.getByText('请输入手机号和 6 位验证码', { exact: true }).waitFor();
          assert(!requests.some(request => /\/me\/tcm-/.test(request.path)));
        }
        await page.screenshot({ path: path.join(out, `${width}x${height}-${loggedIn ? 'report' : 'login'}.png`) });
        await page.goBack();
        await page.locator('.profile-page').waitFor({ state: 'hidden' });
        await page.getByRole('heading', { name: '选择您所在的沙发' }).waitFor();
        assert(!new URL(page.url()).searchParams.has('seat'));
        assert(!requests.some(request => /entry-sessions|occupancies|selection-sessions/.test(request.path)));
        assert(!requests.some(request => request.method !== 'GET' && !/tracking|events/.test(request.path)));
        assert.equal(errors.length, 0);
        results.push({ width, height, loggedIn, noSeatOrSelectionCalls: true, originalLayout: true, lastRowClear: true, historyBack: true, errors });
        await context.close();
      }
    }
    // Existing consent and self-only checks use the real isolated API, not a mocked report list.
    const foreign = await fetch(`${fixture.apiBase}/api/v1/me/tcm-reports/SYNTHETIC-R-other-1`, { headers });
    assert.equal(foreign.status, 404);
    const revoke = await fetch(`${fixture.apiBase}/api/v1/me/tcm-report-consent`, { method: 'DELETE', headers });
    assert(revoke.ok);
    const anonymousReports = await fetch(`${fixture.apiBase}/api/v1/me/tcm-reports`);
    assert.equal(anonymousReports.status, 401);
    const unauthorizedReports = await fetch(`${fixture.apiBase}/api/v1/me/tcm-reports`, { headers });
    assert.equal(unauthorizedReports.status, 403);
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    await context.addInitScript(auth => localStorage.setItem('hxy_diy_customer_auth', JSON.stringify(auth)), fixture.accounts.full);
    await context.route('**/api/v1/stores/1/service-position-map', route => route.fulfill({ json: map }));
    const page = await context.newPage();
    await page.goto(root);
    await page.getByRole('button', { name: '查看我的检测报告', exact: true }).click();
    await page.getByRole('heading', { name: '查看前，请确认授权' }).waitFor();
    assert.equal(await page.locator('.my-reports-list').count(), 0);
    assert(await page.getByRole('button', { name: '同意并查看', exact: true }).isDisabled());
    await page.screenshot({ path: path.join(out, '390-consent-required.png') });
    await context.close();
    if (process.argv[3]) {
      const comparison = await browser.newPage({ viewport: { width: 780, height: 844 } });
      const source = fs.readFileSync(process.argv[3]).toString('base64');
      const actual = fs.readFileSync(path.join(out, '390x844-seat.png')).toString('base64');
      await comparison.setContent(`<style>body{margin:0;display:flex}img{width:390px;height:844px;object-fit:contain}</style><img src="data:image/png;base64,${source}"><img src="data:image/png;base64,${actual}">`);
      await comparison.screenshot({ path: path.join(out, 'reference-vs-implementation.png') });
    }
    fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify({ productionWrites: false, realIsolatedConsent: true, foreignReportStatus: foreign.status, anonymousReportStatus: anonymousReports.status, revokedConsentStatus: unauthorizedReports.status, results }, null, 2));
    console.log(JSON.stringify({ passed: results.length, consentRequired: true, report: path.join(out, 'result.json') }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

// Run only against an isolated backend fixture; never sends SMS or changes production data.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const fixture = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
assert.equal(fixture.synthetic, true);
const out = path.resolve(process.argv[3] || 'output/playwright/tcm-status-entry');
fs.mkdirSync(out, { recursive: true });

(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  const results = [];
  try {
    for (const state of ['released-error', 'expired']) {
      for (const loggedIn of [true, false]) {
        const context = await browser.newContext({ viewport: { width: 375, height: 812 } });
        if (loggedIn) {
          await context.addInitScript(auth => localStorage.setItem('hxy_diy_customer_auth', JSON.stringify(auth)), fixture.accounts.full);
          const response = await context.request.delete('http://127.0.0.1:8022/api/v1/me/tcm-report-consent', { headers: { Authorization: `Bearer ${fixture.accounts.full.token}` } });
          assert.equal(response.status(), 200);
        }
        const page = await context.newPage();
        const requests = [], errors = [];
        page.on('request', request => requests.push({ url: request.url(), method: request.method() }));
        page.on('pageerror', error => errors.push(error.message));
        // Only selection status is simulated; all report/auth/consent routes use the real backend.
        await page.route('**/api/v1/entry-sessions', async route => {
          if (state === 'released-error') return route.fulfill({ status: 410, contentType: 'application/json', body: JSON.stringify({ detail: '本次位置已释放' }) });
          const response = await route.fetch();
          assert.equal(response.status(), 200);
          const body = await response.json();
          body.occupancy.hold_expires_at = '2020-01-01T00:00:00Z';
          await route.fulfill({ response, json: body });
        });
        if (state === 'expired') await page.route('**/api/v1/stores/1/service-position-map*', async route => {
          const response = await route.fetch();
          const body = await response.json();
          for (const position of body.positions) if (position.occupancy) position.occupancy.hold_expires_at = '2020-01-01T00:00:00Z';
          await route.fulfill({ response, json: body });
        });
        await page.goto(fixture.url);
        await page.locator('.status-screen').waitFor();
        assert((await page.locator('.status-screen').innerText()).includes('本次位置已释放'));
        await page.screenshot({ path: path.join(out, `${state}-${loggedIn ? 'logged' : 'anonymous'}-status.png`) });
        requests.length = 0;
        await page.getByRole('button', { name: '我的检测报告', exact: true }).click();
        if (loggedIn) {
          await page.getByRole('checkbox').waitFor();
          assert(!requests.some(request => /\/tcm-reports(?:\?|\/|$)/.test(request.url)));
          await page.screenshot({ path: path.join(out, `${state}-consent.png`) });
          await page.getByRole('checkbox').check();
          await page.getByRole('button', { name: '同意并查看', exact: true }).click();
          await page.getByRole('button', { name: /检测报告.*查看结果/ }).click();
          await page.getByText('合成测试结果', { exact: true }).waitFor();
          assert(!requests.some(request => /send-code|\/login(?:\?|$)/.test(request.url)));
          await page.screenshot({ path: path.join(out, `${state}-report.png`) });
        } else {
          await page.getByPlaceholder('请输入手机号').waitFor();
          assert(!requests.some(request => request.url.includes('tcm-report')));
          const denied = await context.request.get('http://127.0.0.1:8022/api/v1/me/tcm-reports');
          assert.equal(denied.status(), 401);
        }
        assert(!requests.some(request => request.method !== 'GET' && /entry-sessions|occupancies|selection-sessions|orders/.test(request.url)));
        assert(requests.filter(request => request.url.includes('tcm-report')).every(request => !request.url.includes('phone=')));
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        assert.deepEqual(errors, []);
        results.push({ state, loggedIn, realReportApi: true, noSelectionMutation: true, consentGate: true, noExtraOtp: loggedIn, anonymousDenied: !loggedIn, overflow: false });
        await context.close();
      }
    }
    fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify({ synthetic: true, selectionStatusOnlySimulated: true, results }, null, 2));
    console.log(JSON.stringify(results));
  } catch (error) {
    for (const page of browser.contexts().flatMap(context => context.pages())) console.error((await page.locator('body').innerText()).slice(-1000));
    throw error;
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

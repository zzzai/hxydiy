'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.TECHNICIAN_TEST_PLAYWRIGHT || 'playwright');
const { startDenyProxy, createBrowserGuard } = require(process.env.TECHNICIAN_TEST_GUARD);
const origin = process.env.TECHNICIAN_TEST_ORIGIN || 'http://127.0.0.1:18331';
const actor = { id: 1, technician_id: 1, store_id: 1, role: 'technician', name: '测试技师甲' };
async function main() {
  const events = new Map();
  const proxy = await startDenyProxy(new Set([origin]), events);
  let browser;
  let page;
  const diagnostics = { pageErrors: [], httpErrors: [], requests: [], failedResources: [] };
  const report = { scope: 'actual React entry with synthetic HTTP timing only', productionWrites: 0, cases: [] };
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true, proxy: { server: proxy.url, bypass: '<-loopback>' } });
    const guard = await createBrowserGuard(browser, new Set([origin]), events);
    await guard.context.addInitScript(({ actor }) => {
      localStorage.setItem('hxy_admin_token', 'synthetic-t1-token');
      localStorage.setItem('hxy_admin_staff', JSON.stringify(actor));
    }, { actor });
    const requests = diagnostics.requests;
    await guard.context.route('**/api/v1/**', async route => {
      const p = new URL(route.request().url()).pathname;
      requests.push(p);
      const body = p === '/api/v1/auth/wecom/authorize'
        ? { detail: { code: 'WECOM_DISABLED', message: '测试身份核验暂不可用' } }
        : p === '/api/v1/technician/me' ? { staff: actor, technician: { id: 1, name: '测试技师甲' } }
        : { items: [] };
      await route.fulfill({ status: p.includes('/authorize') ? 503 : 200, contentType: 'application/json', body: JSON.stringify(body) });
    });
    page = await guard.context.newPage();
    page.on('requestfailed', request => diagnostics.failedResources.push({ path: new URL(request.url()).pathname, error: request.failure()?.errorText }));
    page.on('pageerror', error => diagnostics.pageErrors.push(error.message.slice(0, 250)));
    page.on('response', response => { if (response.status() >= 400) diagnostics.httpErrors.push({ path: new URL(response.url()).pathname, status: response.status() }); });
    const firstApi = page.waitForRequest(r => new URL(r.url()).pathname.startsWith('/api/v1/'), { timeout: 30000 });
    await page.goto(origin + '/technician/wecom', { waitUntil: 'domcontentloaded' });
    await firstApi;
    await page.getByRole('button').first().waitFor();
    const oldReads = requests.filter(p => p.startsWith('/api/v1/technician/'));
    const authorized = requests.includes('/api/v1/auth/wecom/authorize');
    const result = { name: 'workbench entry rejects residual T1 before loading business', oldBusinessReads: oldReads.length,
      authorizeRequested: authorized, oldIdentityVisible: await page.getByText('测试技师甲', { exact: true }).count() > 0 };
    report.cases.push(result);
    assert.equal(oldReads.length, 0, 'Residual T1 must not issue business reads before the new WeCom identity is verified');
    assert.equal(authorized, true, 'Workbench launch must request identity verification even with a valid DIY token');
    assert.equal(result.oldIdentityVisible, false);
    report.passed = true;
  } catch (error) {
    report.passed = false;
    report.diagnostics = diagnostics;
    if (page) { report.pagePath = new URL(page.url()).pathname; report.bodyPreview = (await page.locator('body').innerText().catch(() => '')).slice(0, 300); }
    report.guardEvents = Object.fromEntries(events);
    report.failure = { type: error.name, code: error.code || 'BROWSER_CHECK_FAILED', message: error instanceof assert.AssertionError ? error.message : 'Inspect the scoped browser test failure' };
  } finally {
    if (browser) await browser.close();
    await proxy.close();
    const out = process.env.TECHNICIAN_TEST_OUTPUT || __dirname;
    await fs.mkdir(out, { recursive: true });
    const file = path.join(out, 'entry-' + Date.now() + '.json');
    await fs.writeFile(file, JSON.stringify(report, null, 2) + '\n');
    process.stdout.write(JSON.stringify({ ...report, receipt: file }) + '\n');
    process.exitCode = report.passed ? 0 : 1;
  }
}
main().catch(() => { process.stderr.write('Test startup failed.\n'); process.exitCode = 1; });

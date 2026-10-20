'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.TECHNICIAN_TEST_PLAYWRIGHT || 'playwright');
const { startDenyProxy, createBrowserGuard } = require(process.env.TECHNICIAN_TEST_GUARD);
const origin = process.env.TECHNICIAN_TEST_ORIGIN || 'http://127.0.0.1:18331';
const actor = { id: 1, technician_id: 1, store_id: 1, role: 'technician', name: '测试技师甲' };
async function verifyRoleHandoffs(browser, events, report, diagnostics) {
  for (const manager of [true, false]) {
    const guard = await createBrowserGuard(browser, new Set([origin]), events);
    report.phase = manager ? 'manager-entry' : 'technician-entry';
    try {
      const requests = [];
      const staff = manager
        ? { id: 3, technician_id: null, store_id: 1, role: 'store_manager', name: '合成店长', store_name: '合成门店' }
        : actor;
      const response = { token: 'synthetic-role-token', staff, auth_method: 'wecom',
        ...(manager ? { selector_token: null, workspaces: [{ assignment_id: 7, role: 'store_manager', scope_type: 'store', scope_id: 1, scope_name: '合成门店' }] } : {}) };
      await guard.context.addInitScript(() => {
        if (location.pathname !== '/technician/wecom/complete') return;
        sessionStorage.setItem('hxy_wecom_pending', JSON.stringify({ attempt_id: 'synthetic-role-attempt', entry_nonce: 'synthetic-role-nonce' }));
        window.addEventListener('pagehide', event => {
          sessionStorage.setItem('synthetic-role-pagehide', event.isTrusted ? 'trusted' : 'synthetic');
        }, { once: true });
      });
      await guard.context.route(origin + '/api/v1/**', async route => {
        const pathname = new URL(route.request().url()).pathname;
        requests.push(pathname);
        if (diagnostics.requests.length < 64) diagnostics.requests.push(pathname);
        const body = pathname.endsWith('/auth/wecom/exchange') ? response
          : pathname.endsWith('/admin/v2/selection-sessions') ? { items: [], total: 0, page: 1, page_size: 20 }
          : pathname.endsWith('/technician/me') ? { staff: actor, technician: { id: 1, name: actor.name } } : { items: [] };
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
      });
      await guard.context.route(origin + '/admin/', route => route.fulfill({
        status: 200, contentType: 'text/html',
        body: '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Synthetic handoff destination</title><h1>合成管理交接页</h1></html>',
      }));
      const rolePage = await guard.context.newPage();
      rolePage.on('requestfailed', request => {
        if (diagnostics.failedResources.length < 16) diagnostics.failedResources.push({ path: new URL(request.url()).pathname, error: request.failure()?.errorText });
      });
      rolePage.on('pageerror', error => {
        if (diagnostics.pageErrors.length < 8) diagnostics.pageErrors.push(error.message.slice(0, 250));
      });
      rolePage.on('response', response => {
        if (response.status() >= 400 && diagnostics.httpErrors.length < 16) diagnostics.httpErrors.push({ path: new URL(response.url()).pathname, status: response.status() });
      });
      await rolePage.goto(origin + '/technician/wecom/complete', { waitUntil: 'commit' });
      if (manager) {
        await rolePage.waitForURL(origin + '/technician/store');
        await rolePage.getByRole('heading', { name: '门店工作台', exact: true }).waitFor();
        await rolePage.getByText('更多', { exact: true }).click();
        await rolePage.getByRole('button', { name: '电脑后台', exact: true }).click();
      } else {
        await rolePage.waitForURL(origin + '/technician/today');
        await rolePage.getByText('目前没有本人正在服务的顾客', { exact: true }).waitFor();
        assert.ok(requests.includes('/api/v1/technician/my-tasks'));
        await rolePage.goto(origin + '/admin/#/today', { waitUntil: 'domcontentloaded' });
      }
      await rolePage.waitForURL(origin + '/admin/#/today');
      await rolePage.getByRole('heading', { name: '合成管理交接页', exact: true }).waitFor();
      const observed = await rolePage.evaluate(() => {
        const current = JSON.parse(localStorage.getItem('hxy_admin_staff') || 'null');
        return {
          tokenPresent: Boolean(localStorage.getItem('hxy_admin_token')),
          roleMatchesManager: current?.role === 'manager',
          storeMatches: current?.store_id === 1,
          noTechnician: current?.technician_id === null,
          wecomMethod: localStorage.getItem('hxy_staff_auth_method') === 'wecom',
          trustedPagehide: sessionStorage.getItem('synthetic-role-pagehide') === 'trusted',
        };
      });
      assert.equal(observed.trustedPagehide, true, 'The role handoff must traverse an actual document pagehide');
      assert.equal(observed.tokenPresent, manager);
      assert.equal(observed.wecomMethod, manager);
      if (manager) {
        assert.equal(observed.roleMatchesManager && observed.storeMatches && observed.noTechnician, true);
        assert.equal(requests.some(pathname => pathname.startsWith('/api/v1/technician/')), false);
      }
      report.cases.push({ name: manager ? 'manager defaults to mobile and keeps its scoped session on explicit desktop handoff without technician requests'
        : 'technician still reaches its own tasks and clears its session on actual document departure', status: 'passed', actualPagehide: true });
    } finally { await guard.context.close(); }
  }
}
async function main() {
  const events = new Map();
  const proxy = await startDenyProxy(new Set([origin]), events);
  let browser;
  let page;
  const diagnostics = { pageErrors: [], httpErrors: [], requests: [], failedResources: [] };
  const report = { scope: 'actual React entry with synthetic HTTP timing only', productionWrites: 0, cases: [] };
  try {
    browser = await chromium.launch({ ...(process.env.TECHNICIAN_TEST_EXECUTABLE ? { executablePath: process.env.TECHNICIAN_TEST_EXECUTABLE } : { channel: 'msedge' }), headless: true, proxy: { server: proxy.url, bypass: '<-loopback>' } });
    if (process.env.TECHNICIAN_TEST_CASE === 'role-handoff') {
      report.scope = 'real React OAuth shell and actual document pagehide; synthetic API and admin destination; not real WeCom, manager UI or BFCache';
      await verifyRoleHandoffs(browser, events, report, diagnostics);
      report.passed = true;
      return;
    }
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
    await verifyRoleHandoffs(browser, events, report, diagnostics);
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
    report.guardEvents = Object.fromEntries(events);
    const out = process.env.TECHNICIAN_TEST_OUTPUT || __dirname;
    await fs.mkdir(out, { recursive: true });
    const file = path.join(out, 'entry-' + Date.now() + '.json');
    await fs.writeFile(file, JSON.stringify(report, null, 2) + '\n');
    process.stdout.write(JSON.stringify({ ...report, receipt: file }) + '\n');
    process.exitCode = report.passed ? 0 : 1;
  }
}
main().catch(() => { process.stderr.write('Test startup failed.\n'); process.exitCode = 1; });

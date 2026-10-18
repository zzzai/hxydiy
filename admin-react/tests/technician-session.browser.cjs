'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.TECHNICIAN_TEST_PLAYWRIGHT || 'playwright');
const { startDenyProxy, createBrowserGuard } = require(process.env.TECHNICIAN_TEST_GUARD);
const origin = process.env.TECHNICIAN_TEST_ORIGIN || 'http://127.0.0.1:18335';
const staff = (id) => ({ id, technician_id: id, store_id: 1, role: 'technician', name: `合成技师${id}` });
const task = (id) => ({ occupancy_id: id, user_id: id, selection_session_id: `synthetic-session-${id}`, occupancy_status: 'in_service', room_id: id, room_name: `合成服务位${id}`, items: [{ name: `合成项目${id}`, quantity: 1, project_id: id }] });
const deferred = () => { let resolve; const promise = new Promise((r) => { resolve = r; }); return { promise, resolve }; };
async function main() {
  const events = new Map();
  const proxy = await startDenyProxy(new Set([origin]), events);
  let browser;
  const report = { scope: 'real React/shared session with synthetic HTTP and lifecycle events, not real WeCom or BFCache roundtrip', productionWrites: 0, cases: [] };
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true, proxy: { server: proxy.url, bypass: '<-loopback>' } });
    async function setup({ pending = false, wecom = false, response }) {
      const guard = await createBrowserGuard(browser, new Set([origin]), events);
      await guard.context.addInitScript(({ actor, pending, wecom }) => {
        localStorage.setItem('hxy_admin_token', 'synthetic-1');
        localStorage.setItem('hxy_admin_staff', JSON.stringify(actor));
        if (wecom) localStorage.setItem('hxy_staff_auth_method', 'wecom');
        if (pending) sessionStorage.setItem('hxy_wecom_pending', JSON.stringify({ entry_nonce: 'synthetic-nonce', attempt_id: 'synthetic-attempt' }));
      }, { actor: staff(1), pending, wecom });
      const requests = [];
      await guard.context.route('**/api/v1/**', async (route) => {
        const p = new URL(route.request().url()).pathname;
        const token = route.request().headers().authorization || '';
        const id = token.endsWith('synthetic-2') ? 2 : 1;
        requests.push({ p, id });
        const custom = await response?.(p, id, route);
        if (custom === true) return;
        const data = p.endsWith('/me') ? { staff: staff(id), technician: { id, name: staff(id).name } }
          : p.endsWith('/my-tasks') ? { items: [task(id)] } : { items: [], total: 0, page: 1, page_size: 20 };
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
      });
      const page = await guard.context.newPage();
      await page.setViewportSize({ width: 390, height: 844 });
      return { page, requests, context: guard.context };
    }
    async function switchActor(page, id = 2) {
      await page.evaluate(async (actor) => {
        const session = await import('/src/wecomSession.ts');
        session.commitStaffSession({ token: `synthetic-${actor.id}`, staff: actor }, session.getSessionEpoch());
      }, staff(id));
    }
    const exchange = deferred();
    const callback = await setup({ pending: true, response: async (p, _id, route) => {
      if (!p.endsWith('/exchange')) return;
      await exchange.promise;
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ token: 'synthetic-2', staff: staff(2), auth_method: 'wecom' }) });
      return true;
    } });
    await callback.page.goto(origin + '/technician/wecom/complete');
    await callback.page.getByRole('heading', { name: '正在验证企业微信身份' }).waitFor();
    assert.equal(callback.requests.filter((r) => r.p.includes('/technician/')).length, 0);
    assert.equal(await callback.page.getByText('合成技师1', { exact: true }).count(), 0);
    exchange.resolve();
    await callback.page.getByText('合成技师2', { exact: true }).waitFor();
    await callback.page.getByText('合成服务位2', { exact: false }).waitFor();
    assert.equal(callback.requests.filter((r) => r.p.includes('/technician/') && r.id === 1).length, 0);
    const authCount = callback.requests.filter((r) => r.p.includes('/auth/wecom/')).length;
    await callback.page.getByRole('navigation', { name: '技师端导航' }).getByText('服务记录', { exact: true }).click();
    await callback.page.getByRole('navigation', { name: '技师端导航' }).getByText('今日服务', { exact: true }).click();
    await callback.page.getByText('合成服务位2', { exact: false }).waitFor();
    assert.equal(callback.requests.filter((r) => r.p.includes('/auth/wecom/')).length, authCount);
    await callback.context.close();
    report.cases.push('pending callback gates all old business; T2 only after exchange; internal navigation no OAuth loop');

    for (const status of [200, 401]) {
      const gate = deferred();
      const started = deferred();
      const run = await setup({ response: async (p, id, route) => {
        if (!p.endsWith('/my-tasks') || id !== 1) return;
        started.resolve(); await gate.promise;
        await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(status === 200 ? { items: [task(1)] } : { detail: 'Synthetic expired actor' }) });
        return true;
      } });
      await run.page.goto(origin + '/technician/today');
      await started.promise;
      await switchActor(run.page);
      await run.page.getByText('合成服务位2', { exact: false }).waitFor();
      const oldResponse = run.page.waitForResponse((r) => r.url().includes('/my-tasks') && r.request().headers().authorization?.endsWith('synthetic-1'));
      gate.resolve(); await oldResponse;
      await run.page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      assert.equal(await run.page.getByText('合成服务位1', { exact: false }).count(), 0);
      assert.equal(await run.page.getByText('合成技师2', { exact: true }).count(), 1);
      assert.equal(await run.page.evaluate(() => localStorage.getItem('hxy_admin_token')), 'synthetic-2');
      await run.context.close();
      report.cases.push(`late T1 ${status} cannot render, clear or redirect T2`);
    }

    const lifecycle = await setup({ wecom: true, response: async (p, _id, route) => {
      if (!p.endsWith('/authorize')) return;
      await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Synthetic provider disabled' }) }); return true;
    } });
    await lifecycle.page.goto(origin + '/technician/today');
    await lifecycle.page.getByText('合成服务位1', { exact: false }).waitFor();
    await lifecycle.page.evaluate(() => window.dispatchEvent(new PageTransitionEvent('pagehide', { persisted: true })));
    assert.equal(await lifecycle.page.getByText('合成技师1', { exact: true }).count(), 0);
    assert.equal(await lifecycle.page.evaluate(() => localStorage.getItem('hxy_admin_token')), null);
    await lifecycle.page.evaluate(() => window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true })));
    await lifecycle.page.getByRole('button', { name: '重新验证', exact: true }).waitFor();
    assert.equal(lifecycle.requests.filter((r) => r.p.endsWith('/authorize')).length, 1);
    await lifecycle.context.close();
    report.cases.push('synthetic BFCache lifecycle clears old DOM/session before reverify (not actual browser cache roundtrip)');
    report.passed = true;
  } catch (error) { report.passed = false; report.failure = { type: error.name, message: error.message.slice(0, 1000) }; }
  finally {
    if (browser) await browser.close();
    await proxy.close();
    const out = process.env.TECHNICIAN_TEST_OUTPUT || __dirname;
    await fs.mkdir(out, { recursive: true });
    const file = path.join(out, 'session-' + Date.now() + '.json');
    await fs.writeFile(file, JSON.stringify(report, null, 2) + '\n');
    process.stdout.write(JSON.stringify({ ...report, receipt: file }) + '\n');
    process.exitCode = report.passed ? 0 : 1;
  }
}
main().catch(() => { process.exitCode = 1; });

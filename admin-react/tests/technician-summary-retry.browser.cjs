'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.TECHNICIAN_TEST_PLAYWRIGHT || 'playwright');
const { startDenyProxy, createBrowserGuard } = require(process.env.TECHNICIAN_TEST_GUARD);
const origin = process.env.TECHNICIAN_TEST_ORIGIN || 'http://127.0.0.1:18335';
const actor = { id: 1, technician_id: 1, store_id: 1, role: 'technician', name: '合成重试技师' };
const task = { occupancy_id: 10, user_id: 7, selection_session_id: 'synthetic-retry-session', occupancy_status: 'in_service', room_id: 1, room_name: '合成服务位', items: [{ name: '合成项目', quantity: 1, project_id: 1 }] };
async function main() {
  const events = new Map();
  const proxy = await startDenyProxy(new Set([origin]), events);
  let browser;
  const report = { scope: 'real React summary retry; synthetic HTTP only', productionWrites: 0, cases: [] };
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true, proxy: { server: proxy.url, bypass: '<-loopback>' } });
    for (const failure of ['http500', 'network']) {
      const guard = await createBrowserGuard(browser, new Set([origin]), events);
      let retryAllowed = false;
      let summaries = 0;
      let details = 0;
      let signalRetry;
      const retried = new Promise((resolve) => { signalRetry = resolve; });
      const result = { name: `${failure} summary retry keeps drawer and loads customer`, passed: false };
      report.cases.push(result);
      try {
        await guard.context.addInitScript((staff) => {
          localStorage.setItem('hxy_admin_token', 'synthetic-retry-token');
          localStorage.setItem('hxy_admin_staff', JSON.stringify(staff));
        }, actor);
        await guard.context.route('**/api/v1/**', async (route) => {
          const p = new URL(route.request().url()).pathname;
          let data;
          if (p.endsWith('/me')) data = { staff: actor, technician: { id: 1, name: actor.name } };
          else if (p.endsWith('/my-tasks')) data = { items: [task] };
          else if (p.endsWith('/customer-summary')) {
            summaries += 1;
            if (!retryAllowed) {
              if (failure === 'network') await route.abort('failed');
              else await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'Synthetic summary failure' }) });
              return;
            }
            signalRetry();
            data = { occupancy_id: 10, customer_id: 7, customer_name: '重试后合成顾客', access: 'granted', membership: { level: null } };
          } else if (p.endsWith('/customer-history')) { details += 1; data = { items: [], total: 0, page: 1, page_size: 20 }; }
          else throw new Error('Unexpected synthetic endpoint: ' + p);
          await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
        });
        const page = await guard.context.newPage();
        await page.setViewportSize({ width: 390, height: 844 });
        await page.goto(origin + '/technician/today');
        await page.getByRole('button', { name: '查看顾客资料', exact: true }).click();
        await page.getByText('资料加载失败，请重试。', { exact: true }).waitFor();
        assert.equal(details, 0, 'Failed summary must not load customer details');
        const before = summaries;
        retryAllowed = true;
        await page.getByRole('button', { name: '重新加载', exact: true }).click();
        const requestedAgain = await Promise.race([
          retried.then(() => true),
          page.getByRole('dialog').waitFor({ state: 'hidden', timeout: 5000 }).then(() => false),
        ]);
        assert.equal(requestedAgain, true, 'Retry must request summary again instead of closing the drawer');
        await page.getByText('重试后合成顾客', { exact: true }).waitFor();
        await page.getByText('暂无服务历史', { exact: true }).waitFor();
        assert.equal(summaries, before + 1, 'One retry click makes exactly one additional summary request');
        assert.equal(await page.getByRole('dialog').isVisible(), true);
        assert.equal(await page.getByText('资料加载失败，请重试。', { exact: true }).count(), 0);
        result.passed = true;
        result.summaryRequestsBefore = before;
        result.summaryRequestsAfter = summaries;
      } catch (error) { result.failure = { type: error.name, message: error.message.slice(0, 700) }; }
      finally { await guard.context.close(); }
    }
    report.passed = report.cases.every((item) => item.passed);
  } finally {
    if (browser) await browser.close();
    await proxy.close();
    const out = process.env.TECHNICIAN_TEST_OUTPUT || __dirname;
    await fs.mkdir(out, { recursive: true });
    const file = path.join(out, 'summary-retry-' + Date.now() + '.json');
    await fs.writeFile(file, JSON.stringify(report, null, 2) + '\n');
    process.stdout.write(JSON.stringify({ ...report, receipt: file }) + '\n');
    process.exitCode = report.passed ? 0 : 1;
  }
}
main().catch(() => { process.exitCode = 1; });

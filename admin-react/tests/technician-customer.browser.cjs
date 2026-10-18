'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.TECHNICIAN_TEST_PLAYWRIGHT || 'playwright');
const { startDenyProxy, createBrowserGuard } = require(process.env.TECHNICIAN_TEST_GUARD);
const origin = process.env.TECHNICIAN_TEST_ORIGIN || 'http://127.0.0.1:18335';
const actor = { id: 1, technician_id: 1, store_id: 1, role: 'technician', name: '合成技师甲' };
const task = { occupancy_id: 10, user_id: 7, selection_session_id: 'synthetic-session', occupancy_status: 'in_service', room_id: 1, room_name: '合成一号位', items: [{ name: '合成服务', quantity: 1, project_id: 1 }] };
async function main() {
  const events = new Map();
  const proxy = await startDenyProxy(new Set([origin]), events);
  let browser;
  const report = { scope: 'real technician React components; synthetic HTTP only; no PG/provider/source claims', productionWrites: 0, cases: [] };
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true, proxy: { server: proxy.url, bypass: '<-loopback>' } });
    const guard = await createBrowserGuard(browser, new Set([origin]), events);
    await guard.context.addInitScript(({ actor }) => {
      localStorage.setItem('hxy_admin_token', 'synthetic-actor-1');
      localStorage.setItem('hxy_admin_staff', JSON.stringify(actor));
    }, { actor });
    const requests = [];
    let revoked = false;
    let released = false;
    await guard.context.route('**/api/v1/**', async (route) => {
      const request = route.request();
      const pathname = new URL(request.url()).pathname;
      const method = request.method();
      requests.push({ pathname, method });
      let status = 200;
      let data;
      if (pathname.endsWith('/technician/me')) data = { staff: actor, technician: { id: 1, name: actor.name } };
      else if (pathname.endsWith('/my-tasks')) data = { items: released ? [] : [task] };
      else if (pathname.endsWith('/customer-summary')) data = { occupancy_id: 10, customer_id: 7, customer_name: '合成顾客', access: 'granted', membership: { level: '普通会员' } };
      else if (pathname.endsWith('/customer-history')) data = { items: [{ id: 90, selection_session_id: 'synthetic-past', service_started_at: null, service_finished_at: '2026-10-01T10:00:00Z', projects: [{ name: '合成历史项目', quantity: 1 }] }], total: 1, page: 1, page_size: 20 };
      else if (pathname.endsWith('/customer-reviews')) data = { items: [
        { id: 1, rating: 5, content: '合成服务评价内容', created_at: '2026-10-01T10:00:00Z', feedback_type: 'service', source: 'completed_service', tags: [], projects: [{ name: '合成评价项目', quantity: 1 }] },
        { id: 1, rating: 4, content: '合成到店反馈内容', created_at: '2026-10-02T10:00:00Z', feedback_type: 'visit', source: 'customer_h5', tags: [], projects: [] },
      ], total: 2, page: 1, page_size: 20 };
      else if (pathname.includes('/customer-reports')) { status = 403; data = { detail: { code: 'REPORT_ACCESS_UNAVAILABLE', message: '无员工用途授权' } }; }
      else if (pathname.includes('/customer-tags/contributions/')) {
        assert.equal(method, 'DELETE');
        assert.deepEqual(request.postDataJSON(), { expected_version: 1, reason: '撤回本人添加的标签' });
        revoked = true; data = { id: 31, version: 2, revoked: true };
      } else if (pathname.endsWith('/customer-tags')) data = { items: [{ id: 2, name: '合成普通标签', color: null, sources: [
        { kind: 'legacy', contribution_id: null, owned_by_me: false, version: null },
        ...(!revoked ? [{ kind: 'contribution', contribution_id: 31, owned_by_me: true, version: 1 }] : []),
      ] }], available_tags: [{ id: 2, name: '合成普通标签', color: null }] };
      else if (pathname.endsWith('/tasks')) data = { items: [] };
      else { status = 404; data = { detail: 'Unexpected synthetic endpoint' }; }
      await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
    });
    const page = await guard.context.newPage();
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(origin + '/technician/today');
    await page.getByRole('navigation', { name: '技师端导航' }).waitFor();
    assert.equal(await page.getByRole('heading', { name: '我的服务', exact: true }).count(), 1, 'Today must show own services, with the store-wide board kept separately');
    await page.getByRole('button', { name: '查看顾客资料', exact: true }).click();
    await page.getByText('合成历史项目', { exact: false }).waitFor();
    assert.equal(requests.some((r) => r.pathname.endsWith('/tasks')), false);
    assert.equal(requests.some((r) => r.pathname.includes('/customer-reports')), false);
    report.cases.push('my tasks distinct from whole-store board; history loaded; no eager reports');
    await page.getByRole('tab', { name: '顾客反馈' }).click();
    await page.getByText('合成服务评价内容', { exact: true }).waitFor();
    await page.getByText('合成到店反馈内容', { exact: true }).waitFor();
    const visit = page.getByRole('article').filter({ hasText: '合成到店反馈内容' });
    assert.match(await visit.innerText(), /到店反馈/);
    assert.doesNotMatch(await visit.innerText(), /合成评价项目/);
    report.cases.push('same-id feedback types both visible; visit has no fabricated project');
    await page.getByRole('tab', { name: '检测报告' }).click();
    await page.getByText('报告暂不可用', { exact: false }).waitFor();
    report.cases.push('report authorization failure stays denied');
    await page.getByRole('tab', { name: '运营标签' }).click();
    await page.getByRole('button', { name: '撤回本人添加', exact: true }).click();
    await page.getByText('已撤回本人添加，其他来源不受影响', { exact: true }).waitFor();
    await page.getByText('合成普通标签', { exact: true }).first().waitFor();
    assert.equal(await page.getByRole('button', { name: '撤回本人添加', exact: true }).count(), 0);
    report.cases.push('own contribution revoke preserves legacy tag');
    released = true;
    await page.getByRole('dialog').waitFor({ state: 'hidden', timeout: 10000 });
    assert.equal(await page.getByText('合成顾客', { exact: true }).count(), 0);
    report.cases.push('released occupancy removes customer dossier');
    await page.getByRole('button', { name: '查看门店服务位', exact: true }).click();
    await page.getByText('当前门店暂无服务位', { exact: true }).waitFor();
    assert.equal(requests.some((r) => r.pathname.endsWith('/tasks')), true);
    report.cases.push('original whole-store entry retained separately');
    assert.deepEqual(errors, []);
    report.passed = true;
  } catch (error) {
    report.passed = false;
    report.failure = { type: error.name, message: error.message.slice(0, 1000) };
  } finally {
    if (browser) await browser.close();
    await proxy.close();
    const out = process.env.TECHNICIAN_TEST_OUTPUT || __dirname;
    await fs.mkdir(out, { recursive: true });
    const file = path.join(out, 'customer-' + Date.now() + '.json');
    await fs.writeFile(file, JSON.stringify(report, null, 2) + '\n');
    process.stdout.write(JSON.stringify({ ...report, receipt: file }) + '\n');
    process.exitCode = report.passed ? 0 : 1;
  }
}
main().catch(() => { process.exitCode = 1; });

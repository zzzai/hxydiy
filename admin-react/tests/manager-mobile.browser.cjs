
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { chromium } = require(process.env.MANAGER_TEST_PLAYWRIGHT || 'playwright');
const origin = 'http://127.0.0.1:18420';
const head = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
if (!/^[a-f0-9]{40}$/.test(head) || head !== process.env.MANAGER_TEST_HEAD) throw new Error('Exact PR head is required');
const out = path.resolve('output/playwright/manager-mobile', head);
const report = { head, productionWrites: 0, passed: false, cases: [], screenshots: [], unexpectedRequests: [], pageErrors: [] };
let browserInstance, context, page, phase = 'startup';
async function eventually(check, label) {
  const until = Date.now() + 10000;
  while (Date.now() < until) {
    if (await check()) return;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(label);
}
async function check(name, run) {
  phase = name;
  await run();
  report.cases.push({ name, passed: true });
}
async function shot(name) {
  const file = name + '.png';
  await page.screenshot({ path: path.join(out, file), fullPage: false, animations: 'disabled' });
  report.screenshots.push(file);
}
async function start(scenario = 'normal', width = 375, route = '/technician/store') {
  await page.setViewportSize({ width, height: 812 });
  await page.goto(origin + route + '?scenario=' + scenario + '&reset=1', { waitUntil: 'domcontentloaded' });
}
const cards = () => page.locator('.manager-selection-card');
const drawer = () => page.locator('.manager-detail-drawer .ant-drawer-content');
const footer = () => page.locator('.manager-detail-actions');
async function loaded() { await cards().first().waitFor(); }
async function closed() { await eventually(async () => !await drawer().isVisible(), 'Drawer must close after success'); }
async function action(label) {
  await footer().getByRole('button', { name: label, exact: true }).click();
}
async function choosePosition() {
  await page.getByRole('combobox', { name: '安排服务位' }).click();
  await page.locator('.ant-select-item-option').filter({ hasText: '1号沙发' }).click();
}
async function noOverflow() {
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'Page must not overflow horizontally');
  if (await drawer().isVisible()) {
    await footer().getByRole('button').first().click({ trial: true });
    const box = await drawer().boundingBox();
    assert.ok(box && box.x >= -1 && box.x + box.width <= page.viewportSize().width + 1, 'Drawer must fit the viewport');
    for (const button of await footer().getByRole('button').all()) {
      const bounds = await button.boundingBox();
      assert.ok(bounds && bounds.height >= 44 && bounds.y >= 0 && bounds.y + bounds.height <= 813, 'Drawer action must be visible and touch-sized: ' + JSON.stringify(bounds));
    }
  }
}
async function slots() {
  return page.evaluate(() => ({
    manager: Boolean(localStorage.getItem('hxy_admin_token')),
    technician: Boolean(localStorage.getItem('hxy_technician_token')),
    trustedDeparture: sessionStorage.getItem('synthetic-pagehide') === 'true',
  }));
}
async function main() {
  await fs.mkdir(out, { recursive: true });
  try {
    browserInstance = await chromium.launch({ headless: true, args: ['--disable-background-networking'] });
    context = await browserInstance.newContext({ viewport: { width: 375, height: 812 }, serviceWorkers: 'block', timezoneId: 'Asia/Shanghai' });
    context.setDefaultTimeout(15000);
    await context.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.origin !== origin || url.pathname.startsWith('/api/')) {
        report.unexpectedRequests.push({ origin: url.origin, path: url.pathname });
        await route.abort('blockedbyclient'); return;
      }
      await route.continue();
    });
    await context.addInitScript(() => {
      if (location.origin !== 'http://127.0.0.1:18420') return;
      window.addEventListener('pagehide', event => sessionStorage.setItem('synthetic-pagehide', String(event.isTrusted)));
    });
    page = await context.newPage();
    page.on('pageerror', error => report.pageErrors.push(error.message.slice(0, 300)));
    for (const width of [375, 390]) await check('layout-' + width, async () => {
      await start('normal', width); await loaded();
      await eventually(async () => await cards().count() === 20, 'First server page must contain 20 selections');
      assert.match(await cards().nth(1).innerText(), /¥0/);
      assert.match(await cards().nth(2).innerText(), /金额待核实/);
      await noOverflow(); await shot('store-' + width);
      await cards().first().click(); await drawer().waitFor(); await noOverflow(); await shot('detail-' + width);
      await page.getByRole('button', { name: 'Close', exact: true }).click();
      await page.locator('.ant-pagination-next button').click();
      await eventually(async () => await cards().count() === 7, 'Second server page must contain the remaining 7 selections');
      assert.match(await cards().first().innerText(), /0021/);
    });
    await check('empty-and-load-error', async () => {
      await start('empty'); await page.getByText('暂无待确认选单', { exact: true }).waitFor();
      assert.equal(await page.locator('.manager-changes').count(), 0); await noOverflow(); await shot('empty-375');
      await start('error'); await page.getByText('合成网络错误，请重试', { exact: true }).waitFor();
      await page.getByRole('button', { name: '重试', exact: true }).click();
      assert.equal(await cards().count(), 0); await noOverflow(); await shot('load-error-375');
    });
    await check('confirm-and-cancel', async () => {
      for (const label of ['确认选单', '取消选单']) {
        await start(); await loaded(); await cards().first().click(); await action(label);
        if (label === '确认选单') await footer().getByRole('button', { name: label, exact: true }).dblclick();
        else await action(label);
        await closed();
        await page.getByText('共 26 份选单', { exact: true }).waitFor();
        assert.equal(await cards().filter({ hasText: 'ion-0001' }).count(), 0);
        assert.match(await page.locator('aside').innerText(), /操作 1/);
      }
    });
    await check('assign-only-available-position', async () => {
      await start(); await loaded(); await cards().first().click(); await action('安排座位');
      await page.getByRole('combobox', { name: '安排服务位' }).click();
      assert.equal(await page.locator('.ant-select-item-option').filter({ hasText: '2号沙发' }).count(), 0);
      await page.locator('.ant-select-item-option').filter({ hasText: '1号沙发' }).click();
      await action('安排座位'); await closed();
      await eventually(async () => /1号沙发/.test(await cards().first().innerText()), 'Assigned position must survive the post-action list reload');
    });
    await check('addon-identity-approve-reject', async () => {
      await start(); await loaded();
      const rows = page.locator('.manager-change-row');
      assert.equal(await rows.count(), 2);
      assert.match(await rows.nth(0).innerText(), /0029/); assert.match(await rows.nth(1).innerText(), /0030/);
      await rows.first().click(); await drawer().waitFor(); await noOverflow(); await shot('addon-375');
      await action('确认加选'); await action('确认加选'); await closed();
      await eventually(async () => await rows.count() === 1, 'Approved add-on must leave pending list');
      assert.match(await rows.first().innerText(), /0030/);
      await rows.first().click(); await action('拒绝加选'); await action('拒绝加选');
      await page.getByText('请填写拒绝原因', { exact: true }).waitFor();
      await page.getByRole('textbox', { name: '拒绝原因' }).fill('合成验收：顾客取消加选');
      await action('拒绝加选'); await closed();
      await eventually(async () => await page.locator('.manager-changes').count() === 0, 'No empty add-on card after all requests are handled');
    });
    await check('conflict-preserves-position-and-reason', async () => {
      await start('conflict'); await loaded(); await cards().first().click(); await action('安排座位'); await choosePosition(); await action('安排座位');
      await page.getByText('合成冲突：服务状态已变化，请核对后重试', { exact: true }).waitFor();
      assert.match(await drawer().innerText(), /1号沙发/); await shot('conflict-375');
      await page.getByRole('button', { name: 'Close', exact: true }).click();
      await page.locator('.manager-change-row').first().click(); await action('拒绝加选');
      await page.getByRole('textbox', { name: '拒绝原因' }).fill('合成保留原因');
      await action('拒绝加选');
      await page.getByText('合成冲突：服务状态已变化，请核对后重试', { exact: true }).waitFor();
      assert.equal(await page.getByRole('textbox', { name: '拒绝原因' }).inputValue(), '合成保留原因');
    });
    await check('forbidden-disables-and-expired-clears', async () => {
      await start('forbidden'); await loaded(); await cards().first().click(); await action('确认选单'); await action('确认选单');
      await page.getByText('合成权限拒绝', { exact: true }).waitFor();
      assert.equal(await footer().getByRole('button', { name: '确认选单', exact: true }).isDisabled(), true);
      await start('expired');
      await page.waitForURL('**/technician/store/login');
      await page.getByRole('button', { name: '登录移动工作台', exact: true }).waitFor();
      assert.deepEqual({ manager: (await slots()).manager, technician: (await slots()).technician }, { manager: false, technician: true });
      assert.equal(await page.locator('.manager-store-page').count(), 0);
    });
    await check('write-invalidates-delayed-old-read', async () => {
      await start('race'); await loaded();
      await page.getByRole('button', { name: '挂起下次列表读取（合成）', exact: true }).click();
      await page.getByRole('button', { name: '刷新门店选单', exact: true }).click();
      await cards().first().click(); await action('确认选单'); await action('确认选单');
      await closed(); await page.getByText('共 26 份选单', { exact: true }).waitFor();
      await eventually(async () => /旧读释放 true/.test(await page.locator('aside').innerText()), 'Delayed pre-write response must be released');
      assert.equal(await cards().filter({ hasText: 'ion-0001' }).count(), 0);
      assert.equal(await page.getByText('共 26 份选单', { exact: true }).count(), 1);
      await shot('post-write-race-375');
    });
    await check('manager-callback-retains-technician', async () => {
      await start('callback', 375, '/technician/wecom/complete');
      await page.waitForURL('**/technician/store'); await loaded();
      assert.deepEqual({ manager: (await slots()).manager, technician: (await slots()).technician }, { manager: true, technician: true });
      assert.match(await page.locator('aside').innerText(), /技师接口 0/);
    });
    await check('interrupted-callback-real-pagehide', async () => {
      await start('callback-wait', 375, '/technician/wecom/complete');
      await page.getByRole('heading', { name: '正在验证企业微信身份', exact: true }).waitFor();
      await page.getByRole('link', { name: '离开回调（合成）', exact: true }).click();
      await page.waitForURL('**/fixture-left');
      assert.deepEqual(await slots(), { manager: false, technician: true, trustedDeparture: true });
      await page.goBack({ waitUntil: 'domcontentloaded' });
      await eventually(async () => await page.locator('.technician-login-page').count() === 1, 'Interrupted callback must not restore business data');
      assert.equal(await page.locator('.manager-store-page').count(), 0);
      assert.equal((await slots()).technician, true);
    });
    await check('logout-and-technician-isolation', async () => {
      await start(); await loaded(); await page.getByText('更多', { exact: true }).click();
      await page.getByRole('button', { name: '退出登录', exact: true }).click();
      await page.waitForURL('**/technician/store/login');
      assert.equal((await slots()).manager, false); assert.equal((await slots()).technician, true);
      await page.goto(origin + '/technician/today?scenario=technician', { waitUntil: 'domcontentloaded' });
      await page.getByText('目前没有本人正在服务的顾客', { exact: true }).waitFor();
      assert.equal(await page.locator('.manager-store-page').count(), 0);
    });
    await check('other-tab-switch-clears-open-detail', async () => {
      await start(); await loaded(); await cards().first().click(); await drawer().waitFor();
      const peer = await context.newPage();
      await peer.goto(origin + '/technician/store?scenario=normal', { waitUntil: 'domcontentloaded' });
      await peer.getByRole('button', { name: '换店长（合成）', exact: true }).click();
      await page.getByText('另一位合成店长', { exact: true }).waitFor();
      await eventually(async () => !await drawer().isVisible(), 'Identity switch must discard the old detail');
      assert.equal(await page.getByText('合成二店', { exact: true }).count(), 1);
      await peer.close();
    });
    await check('desktop-is-explicit-and-password-return-is-usable', async () => {
      for (const password of [false, true]) {
        await start(); await loaded();
        if (password) {
          await page.getByText('更多', { exact: true }).click(); await page.getByRole('button', { name: '退出登录', exact: true }).click();
          await page.getByRole('textbox', { name: '账号', exact: true }).fill('synthetic-manager');
          await page.getByLabel('密码', { exact: true }).fill('synthetic-password');
          await page.getByRole('button', { name: '登录移动工作台', exact: true }).click(); await loaded();
        }
        await page.getByText('更多', { exact: true }).click(); await page.getByRole('button', { name: '电脑后台', exact: true }).click();
        await page.waitForURL('**/admin/#/today');
        assert.equal((await slots()).manager, true); assert.equal((await slots()).trustedDeparture, true);
        if (password) {
          await page.goBack({ waitUntil: 'domcontentloaded' });
          await loaded();
        }
      }
    });
    assert.deepEqual(report.unexpectedRequests, [], 'Only loopback assets are permitted; no real API calls');
    assert.deepEqual(report.pageErrors, [], 'No browser runtime errors');
    report.passed = true;
  } catch (error) {
    report.failure = { phase, type: error.name, message: error.message.slice(0, 700) };
    if (page && !page.isClosed()) await shot('failure').catch(() => undefined);
  } finally {
    if (browserInstance) await browserInstance.close();
    await fs.writeFile(path.join(out, 'report.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify({ head, passed: report.passed, cases: report.cases.length, report: path.join(out, 'report.json'), failure: report.failure }));
    process.exitCode = report.passed ? 0 : 1;
  }
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });

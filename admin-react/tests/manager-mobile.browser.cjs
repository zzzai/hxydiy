const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.MANAGER_TEST_PLAYWRIGHT || 'playwright');

const head = process.env.MANAGER_TEST_HEAD;
const origin = 'http://127.0.0.1:18420';
const out = path.join('output/playwright/manager-mobile', head);
if (!/^[a-f0-9]{40}$/.test(head) || head !== process.env.MANAGER_TEST_HEAD) throw new Error('Exact PR head is required');

const report = { head, productionWrites: 0, passed: false, cases: [], screenshots: [], unexpectedRequests: [], pageErrors: [] };
let browserInstance, context, page, phase = 'startup';

async function check(name, fn) {
  phase = name;
  try { await fn(); report.cases.push({ name, passed: true }); }
  catch (failure) {
    report.cases.push({ name, passed: false, failure: failure.message.slice(0, 700) });
    if (page && !page.isClosed()) await shot('failure-' + report.cases.length).catch(() => undefined);
  }
}
async function shot(name) {
  const file = name + '.png';
  await page.screenshot({ path: path.join(out, file), fullPage: false, animations: 'disabled' });
  report.screenshots.push(file);
}
async function start(scenario = 'normal', width = 375, route = '/technician/store') {
  await page.setViewportSize({ width, height: 812 });
  await page.goto(origin + route + '?scenario=' + scenario + '&reset=1', { waitUntil: 'domcontentloaded' });
  await page.locator('aside').waitFor();
}
async function loaded() { await page.locator('.manager-p0-page').waitFor(); }
async function tab(label) { await page.locator('.manager-p0-nav button').filter({ hasText: label }).click(); }
async function noOverflow() {
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'Page must not overflow horizontally');
  for (const button of await page.locator('.manager-p0-nav button').all()) {
    const box = await button.boundingBox();
    assert.ok(box && box.height >= 44, 'Bottom nav must be touch-sized');
  }
}
async function slots() {
  return page.evaluate(() => ({
    manager: Boolean(localStorage.getItem('hxy_admin_token')),
    technician: Boolean(localStorage.getItem('hxy_technician_token')),
    trustedDeparture: sessionStorage.getItem('synthetic-pagehide') === 'true',
  }));
}
async function fixtureControl(name) {
  await page.locator('aside').getByRole('button', { name, exact: true }).evaluate((button) => button.click());
}

async function main() {
  await fs.mkdir(out, { recursive: true });
  try {
    browserInstance = await chromium.launch({ headless: true, args: ['--disable-background-networking'] });
    context = await browserInstance.newContext({ viewport: { width: 375, height: 812 }, serviceWorkers: 'block', timezoneId: 'Asia/Shanghai' });
    context.setDefaultTimeout(15000);
    await context.route('**/*', async (route) => {
      const url = new URL(route.request().url());
      if (url.origin !== origin || url.pathname.startsWith('/api/')) {
        report.unexpectedRequests.push({ origin: url.origin, path: url.pathname });
        await route.abort('blockedbyclient');
        return;
      }
      await route.continue();
    });
    await context.addInitScript(() => {
      if (location.origin !== 'http://127.0.0.1:18420') return;
      window.addEventListener('pagehide', (event) => sessionStorage.setItem('synthetic-pagehide', String(event.isTrusted)));
    });
    page = await context.newPage();
    page.on('pageerror', (error) => report.pageErrors.push(error.message.slice(0, 300)));

    for (const width of [375, 390]) await check('layout-' + width, async () => {
      await start('normal', width); await loaded();
      assert.equal(await page.locator('.manager-p0-page').count(), 1);
      assert.equal(await page.locator('.manager-p0-nav button').count(), 4);
      assert.match(await page.locator('.manager-p0-page').innerText(), /今日|现场|团队|经营/);
      await noOverflow(); await shot('today-' + width);
      await tab('经营'); await page.locator('.manager-p0-area').first().waitFor();
      assert.equal(await page.locator('.manager-p0-area').count(), 5);
      await noOverflow(); await shot('ops-' + width);
    });

    await check('team-overview', async () => {
      await start('normal'); await loaded(); await tab('团队');
      await page.locator('.manager-p0-tech').first().waitFor();
      assert.equal(await page.locator('.manager-p0-tech').count(), 2);
      assert.match(await page.locator('.manager-p0-page').innerText(), /学习与考核|待总部抽检|待跟进/);
      await shot('team-375');
    });

    await check('positions-readonly', async () => {
      await start('positions'); await loaded(); await tab('现场');
      await page.locator('.manager-position-card').first().waitFor();
      assert.equal(await page.locator('.manager-position-card').count(), 25);
      assert.equal(await page.locator('.manager-position-view').getByRole('button', { name: /安排座位|开始服务|结束服务/ }).count(), 0);
      const card = page.getByRole('button', { name: '查看2号沙发详情', exact: true });
      await card.scrollIntoViewIfNeeded();
      await noOverflow(); await shot('positions-375');
      await card.click(); await page.locator('.ant-drawer-content').waitFor();
      for (const name of ['确认选单', '取消选单', '安排座位', '开始服务', '结束服务']) {
        assert.equal(await page.locator('.ant-drawer-content').getByRole('button', { name, exact: true }).count(), 0);
      }
      await page.keyboard.press('Escape');
    });

    await check('positions-empty-and-error', async () => {
      await start('positions-empty'); await loaded(); await tab('现场');
      await page.getByText('尚未配置服务位', { exact: true }).waitFor();
      await start('positions-error'); await loaded(); await tab('现场');
      await page.getByText('座位加载失败', { exact: true }).waitFor();
    });

    await check('manager-callback-retains-technician', async () => {
      await start('callback', 375, '/technician/wecom/complete');
      await page.waitForURL('**/technician/store'); await loaded();
      assert.deepEqual({ manager: (await slots()).manager, technician: (await slots()).technician }, { manager: true, technician: true });
    });

    await check('logout-and-technician-isolation', async () => {
      await start(); await loaded(); await page.getByText('更多', { exact: true }).click();
      await page.getByRole('button', { name: '退出登录', exact: true }).click();
      await page.waitForURL('**/technician/store/login');
      assert.equal((await slots()).manager, false);
      assert.equal((await slots()).technician, true);
      assert.equal(await page.locator('.manager-p0-page').count(), 0);
    });

    await check('desktop-entry-is-explicit', async () => {
      await start(); await loaded(); await page.getByText('更多', { exact: true }).click();
      await page.getByRole('button', { name: '电脑后台', exact: true }).click();
      await page.waitForURL('**/admin/#/today');
      assert.equal((await slots()).manager, true);
      assert.equal((await slots()).trustedDeparture, true);
    });

    assert.deepEqual(report.unexpectedRequests, [], 'Only loopback assets are permitted; no real API calls');
    assert.deepEqual(report.pageErrors, [], 'No browser runtime errors');
    report.passed = report.cases.every((item) => item.passed);
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

main().catch((error) => { console.error(error.message); process.exitCode = 1; });

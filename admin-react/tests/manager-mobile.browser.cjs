
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
let resetPending = false;
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
  try {
    await run();
    if (await page.locator('aside').count()) assert.match(await page.locator('aside').innerText(), /非白名单 0/);
    report.cases.push({ name, passed: true });
  } catch (error) {
    const failure = { phase: name, type: error.name, message: error.message.slice(0, 700) };
    report.cases.push({ name, passed: false, failure });
    report.failure ||= failure;
    await shot('failure-' + report.cases.length).catch(() => undefined);
    if (report.unexpectedRequests.length || resetPending) throw error;
  } finally {
    for (const peer of context.pages()) if (peer !== page) await peer.close();
  }
}
async function shot(name) {
  const file = name + '.png';
  await page.screenshot({ path: path.join(out, file), fullPage: false, animations: 'disabled' });
  report.screenshots.push(file);
}
async function start(scenario = 'normal', width = 375, route = '/technician/store') {
  resetPending = true;
  await page.setViewportSize({ width, height: 812 });
  await page.goto(origin + route + '?scenario=' + scenario + '&reset=1', { waitUntil: 'domcontentloaded' });
  await page.locator('aside').waitFor();
  resetPending = false;
}
const cards = () => page.locator('.manager-selection-card');
const drawer = () => page.locator('.manager-detail-drawer:visible .ant-drawer-content');
const footer = () => page.locator('.manager-detail-drawer:visible .manager-detail-actions');
const positionCards = () => page.locator('.manager-position-card');
const positionCard = name => positionCards().filter({ has: page.getByRole('heading', { name, exact: true }) });
async function positionView(expectCards = true) {
  await page.getByRole('button', { name: '座位', exact: true }).click();
  if (expectCards) await positionCards().first().waitFor();
}
async function fixtureControl(name) {
  await page.locator('aside').getByRole('button', { name, exact: true }).evaluate(button => button.click());
}
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
      await page.locator('.manager-detail-drawer:visible').waitFor({ state: 'hidden' });
      await page.locator('.ant-pagination-next button').click();
      await eventually(async () => await cards().count() === 16, 'Second server page must contain the remaining 16 selections');
      assert.match(await cards().first().innerText(), /0021/);
    });
    await check('empty-and-load-error', async () => {
      await start('empty'); await page.getByText('暂无订单', { exact: true }).waitFor();
      assert.equal(await page.locator('.manager-changes').count(), 0); await noOverflow(); await shot('empty-375');
      await start('error'); await page.getByText('合成网络错误，请重试', { exact: true }).waitFor();
      await page.getByRole('button', { name: /重\s*试/ }).click();
      assert.equal(await cards().count(), 0); await noOverflow(); await shot('load-error-375');
    });
    await check('readonly-detail-and-no-pending-actions', async () => {
      await start(); await loaded();
      assert.equal(await page.locator('.manager-changes').count(), 0, 'Add-on approval is no longer a manager action');
      assert.equal(await page.locator('.manager-filter-row').count(), 0, 'Pending/assignment filters are removed');
      assert.match(await cards().first().innerText(), /新订单|已确认/);
      await cards().first().click(); await drawer().waitFor(); await noOverflow(); await shot('readonly-detail-375');
      for (const name of ['确认选单', '取消选单', '安排座位', '确认加选', '拒绝加选']) {
        assert.equal(await drawer().getByRole('button', { name, exact: true }).count(), 0);
      }
      await page.getByRole('button', { name: '关闭详情', exact: true }).click();
    });
    await check('forbidden-and-expired', async () => {
      await start('forbidden'); await loaded();
      assert.equal(await page.locator('.manager-filter-row').count(), 0);
      assert.equal(await page.locator('.manager-changes').count(), 0);
      await start('expired');
      await page.waitForURL('**/technician/store/login');
      await page.getByRole('button', { name: '登录移动工作台', exact: true }).waitFor();
      assert.deepEqual({ manager: (await slots()).manager, technician: (await slots()).technician }, { manager: false, technician: true });
      assert.equal(await page.locator('.manager-store-page').count(), 0);
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
      await peer.addInitScript(() => { if (location.origin === 'http://127.0.0.1:18420') sessionStorage.setItem('manager-fixture-ready', '1'); });
      await peer.goto(origin + '/technician/store?scenario=normal', { waitUntil: 'domcontentloaded' });
      assert.equal(await drawer().isVisible(), true, 'Peer setup must not clear the first tab before identity changes');
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
          await page.getByPlaceholder('请输入店长账号', { exact: true }).fill('synthetic-manager');
          await page.getByPlaceholder('请输入密码', { exact: true }).fill('synthetic-password');
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

    for (const width of [375, 390]) await check('positions-layout-and-readonly-' + width, async () => {
      await start('positions', width); await loaded(); await positionView();
      assert.equal(await positionCards().count(), 25, 'Full map must not inherit selection pagination');
      for (const group of ['沙发', '房间']) assert.equal(await page.getByRole('region', { name: group, exact: true }).count(), 1);
      assert.match(await positionCard('1号沙发').innerText(), /暂无当前选单/);
      assert.doesNotMatch(await page.locator('.manager-position-view').innerText(), /空闲|不应展示的错误关联项目/);
      assert.match(await positionCard('4号床位').innerText(), /已结束服务 · 待离位确认/);
      assert.match(await positionCard('5号房间').innerText(), /已结束服务 · 清洁中/);
      assert.match(await positionCard('6号床位').innerText(), /¥0/);
      assert.match(await positionCard('7号床位').innerText(), /金额待核实/);
      assert.match(await positionCard('8号房间').innerText(), /关联待核实/);
      assert.equal(await positionCard('8号房间').getByRole('button').count(), 0);
      assert.equal(await page.locator('.manager-position-disabled').getByRole('button', { name: '查看3号沙发详情' }).count(), 1);
      for (const button of await page.locator('.manager-view-tabs button').all()) assert.ok((await button.boundingBox()).height >= 44);
      const cardButton = page.getByRole('button', { name: '查看2号沙发详情', exact: true });
      await cardButton.scrollIntoViewIfNeeded(); assert.ok((await cardButton.boundingBox()).height >= 44);
      await noOverflow(); await shot('positions-' + width);
      await cardButton.click(); await drawer().waitFor(); await noOverflow();
      assert.match(await drawer().innerText(), /肩颈多按一会|只读/);
      for (const name of ['确认选单', '取消选单', '安排座位', '开始服务', '结束服务']) assert.equal(await drawer().getByRole('button', { name, exact: true }).count(), 0);
      await shot('position-detail-' + width);
    });
    await check('positions-empty-error-and-store-mismatch', async () => {
      await start('positions-empty'); await loaded(); await positionView(false);
      await page.getByText('尚未配置服务位', { exact: true }).waitFor(); assert.equal(await positionCards().count(), 0);
      await start('positions-error'); await loaded(); await positionView(false);
      await page.getByText('座位加载失败', { exact: true }).waitFor(); assert.equal(await positionCards().count(), 0);
      assert.equal(await page.getByText('暂无当前选单', { exact: true }).count(), 0);
      await shot('positions-error-375');
      await fixtureControl('恢复座位读取（合成）'); await page.getByRole('button', { name: /重\s*试/ }).click();
      await positionCards().first().waitFor(); assert.equal(await positionCards().count(), 25);
      await start('positions-wrong-store'); await loaded(); await positionView(false);
      await page.getByText('座位加载失败', { exact: true }).waitFor(); assert.equal(await positionCards().count(), 0);
    });
    await check('position-detail-never-switches-to-another-order', async () => {
      await start('positions'); await loaded(); await positionView();
      await page.getByRole('button', { name: '查看2号沙发详情', exact: true }).click(); await drawer().waitFor();
      await fixtureControl('更换座位选单（合成）'); await action('刷新座位');
      await drawer().getByText('关联已变化', { exact: true }).waitFor();
      assert.doesNotMatch(await drawer().innerText(), /新关联选单项目|招牌草本泡|¥89/);
      await action('刷新座位'); await drawer().getByText('关联已变化', { exact: true }).waitFor();
      await noOverflow(); await shot('position-changed-375');
      await action('关闭详情'); await closed();
      await page.getByRole('button', { name: '查看2号沙发详情', exact: true }).click();
      await drawer().getByText('新关联选单项目', { exact: false }).waitFor();
    });
    await check('positions-late-read-cannot-replace-new-map', async () => {
      await start('positions'); await loaded(); await positionView();
      await fixtureControl('挂起下次座位读取（合成）'); await page.getByRole('button', { name: '刷新门店座位', exact: true }).click();
      await eventually(async () => /座位挂起 true/.test(await page.locator('aside').innerText()), 'Old map must be pending');
      await fixtureControl('更换座位选单（合成）'); await page.getByRole('button', { name: '刷新门店座位', exact: true }).click();
      await eventually(async () => /新关联选单项目/.test(await positionCard('2号沙发').innerText()), 'Newer map must arrive first');
      await fixtureControl('释放旧座位读取（合成）');
      await eventually(async () => /座位释放 true/.test(await page.locator('aside').innerText()), 'Old map must be released');
      assert.match(await positionCard('2号沙发').innerText(), /新关联选单项目/);
      assert.doesNotMatch(await positionCard('2号沙发').innerText(), /合成长项目名称/);
    });
    await check('positions-identity-switch-discards-detail-and-old-map', async () => {
      await start('positions'); await loaded(); await positionView();
      await fixtureControl('挂起下次座位读取（合成）'); await page.getByRole('button', { name: '刷新门店座位', exact: true }).click();
      await eventually(async () => /座位挂起 true/.test(await page.locator('aside').innerText()), 'Store-one map must be pending');
      await page.getByRole('button', { name: '查看2号沙发详情', exact: true }).click(); await drawer().waitFor();
      await fixtureControl('换店长（合成）'); await page.getByText('另一位合成店长', { exact: true }).waitFor();
      await eventually(async () => !await drawer().isVisible(), 'Store switch must close old position detail');
      await positionView();
      await page.getByRole('heading', { name: '二店·2号沙发', exact: true }).waitFor();
      await fixtureControl('释放旧座位读取（合成）');
      await eventually(async () => /座位释放 true/.test(await page.locator('aside').innerText()), 'Store-one late map must finish');
      assert.equal(await positionCard('2号沙发').count(), 0); assert.equal(await positionCard('二店·2号沙发').count(), 1);
    });
    await check('positions-logout-and-pagehide-do-not-resurrect-map', async () => {
      await start('positions'); await loaded(); await positionView();
      await fixtureControl('挂起下次座位读取（合成）'); await page.getByRole('button', { name: '刷新门店座位', exact: true }).click();
      await eventually(async () => /座位挂起 true/.test(await page.locator('aside').innerText()), 'Map must be pending before logout');
      await page.getByText('更多', { exact: true }).click(); await page.getByRole('button', { name: '退出登录', exact: true }).click();
      await page.waitForURL('**/technician/store/login'); await fixtureControl('释放旧座位读取（合成）');
      await eventually(async () => /座位释放 true/.test(await page.locator('aside').innerText()), 'Late map must settle after logout');
      assert.equal(await positionCards().count(), 0); assert.equal((await slots()).technician, true);
      await start('positions'); await loaded(); await positionView();
      await page.getByRole('link', { name: '离开座位（合成）', exact: true }).click();
      await page.waitForURL('**/fixture-left'); assert.equal((await slots()).trustedDeparture, true);
      await page.goBack({ waitUntil: 'domcontentloaded' });
      await eventually(async () => await page.locator('.technician-login-page').count() === 1, 'Return must not resurrect an invalid WeCom map');
      assert.equal(await positionCards().count(), 0);
    });
    await check('selection-view-remains-readonly-after-position-view', async () => {
      await start('positions'); await loaded(); await positionView();
      await page.getByRole('button', { name: '订单', exact: true }).click(); await loaded();
      await cards().first().click(); await drawer().waitFor();
      for (const name of ['确认选单', '取消选单', '安排座位']) assert.equal(await drawer().getByRole('button', { name, exact: true }).count(), 0);
      await page.getByRole('button', { name: '关闭详情', exact: true }).click();
    });

    assert.deepEqual(report.unexpectedRequests, [], 'Only loopback assets are permitted; no real API calls');
    assert.deepEqual(report.pageErrors, [], 'No browser runtime errors');
    report.passed = report.cases.every(item => item.passed);
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

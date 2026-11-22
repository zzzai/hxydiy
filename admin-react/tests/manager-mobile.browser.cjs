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
    browserInstance = await chromium.launch({ headless: true, channel: 'chromium', args: ['--disable-background-networking', '--use-fake-device-for-media-stream'] });
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
      assert.match(await page.locator('.manager-p0-page').innerText(), /今日|现场|券|我的/);
      await noOverflow(); await shot('today-' + width);
      await page.getByRole('button', { name: /巡检照片/ }).click(); await page.locator('.manager-p0-area').first().waitFor();
      assert.equal(await page.locator('.manager-p0-area').count(), 6);
      await noOverflow(); await shot('ops-' + width);
    });

    await check('inspection-live-camera-only-and-retake', async () => {
      await start('inspection-photos'); await loaded();
      await page.getByRole('button', { name: /巡检照片/ }).click();
      const area = page.locator('.manager-p0-area[aria-label="煮药区"]');
      const camera = area.getByRole('button', { name: '现场拍照' });
      assert.equal(await page.getByText('从相册选').count(), 0);
      assert.equal(await page.locator('.manager-p0-area-grid input[type=file]').count(), 0);
      await context.grantPermissions([], { origin });
      await camera.click();
      await page.getByRole('alert').filter({ hasText: /允许访问相机/ }).waitFor();
      assert.equal(await page.getByRole('button', { name: '拍摄并保存' }).count(), 0);
      await context.grantPermissions(['camera'], { origin });
      await page.getByRole('button', { name: '重试相机' }).click();
      const shoot = async () => {
        await page.getByRole('button', { name: '拍摄并保存' }).click();
        await page.getByRole('dialog').waitFor({ state: 'hidden' });
      };
      await shoot();
      await area.getByText('1 张', { exact: true }).waitFor();
      for (let count = 2; count <= 3; count++) {
        await camera.click(); await shoot();
        await area.getByText(count + ' 张', { exact: true }).waitFor();
      }
      assert.equal(await camera.count(), 0);
      assert.equal(await area.getByRole('img', { name: /煮药区照片/ }).count(), 3);
      page.once('dialog', dialog => dialog.accept());
      await area.getByRole('button', { name: '更换煮药区第 2 张' }).click();
      await shoot();
      await area.getByRole('button', { name: '更换煮药区第 2 张' }).waitFor();
      await page.waitForFunction(() => !document.querySelector('.manager-p0-area[aria-label="煮药区"] button')?.disabled);
      assert.match(await page.locator('.manager-p0-progress-card h2').innerText(), /4\/6/);
      await noOverflow();
    });

    await check('inspection-ai-automatic-current-and-past-photos', async () => {
      await start('inspection-ai'); await loaded();
      await page.getByRole('button', { name: /巡检照片/ }).click();
      const area = page.locator('.manager-p0-area[aria-label="卫生间"]');
      await area.getByText('等待自动审核').waitFor();
      assert.equal(await page.getByRole('button', { name: /审核这张照片|重试初审|送审/ }).count(), 0);
      await area.getByText('AI 审核 · 需整改').waitFor({ timeout: 26000 });
      await area.getByText('洗手台左侧 · 台面散落纸巾').waitFor();
      await area.getByText('清走纸巾后擦净台面').waitFor();
      await noOverflow(); await shot('inspection-automatic-result');
      await area.getByRole('button', { name: '结果有误' }).click();
      await area.getByRole('combobox', { name: '更正结论' }).selectOption('pass');
      await area.getByRole('button', { name: '保存更正' }).click();
      await area.getByText('店长更正 · 通过').waitFor();
      await area.getByText('AI 审核 · 需整改').waitFor();
      page.once('dialog', dialog => dialog.accept());
      await context.grantPermissions(['camera'], { origin });
      await area.getByRole('button', { name: '更换卫生间第 1 张' }).click();
      await page.getByRole('button', { name: '拍摄并保存' }).click();
      await area.getByText('等待自动审核').waitFor();
      assert.equal(await area.getByText('店长更正 · 通过').count(), 0);
      assert.equal(await area.getByText('AI 审核 · 需整改').count(), 0);
      await page.getByRole('button', { name: '查看过往巡检照片' }).click();
      const history = page.locator('.inspection-history');
      await history.getByText('等待自动审核').waitFor();
      assert.equal(await history.getByRole('button', { name: /拍照|更换|送审|审核这张照片/ }).count(), 0);
      await history.getByText('AI 审核 · 通过').waitFor({ timeout: 20000 });
      await history.getByText('接水台 · 水桶摆放整齐').waitFor();
      assert.match(await page.locator('aside').innerText(), /非白名单 0/);
    });

    await check('wecom-swipe-back-stays-in-manager', async () => {
      await start('normal'); await loaded();
      await tab('现场');
      await page.goBack({ waitUntil: 'commit' }).catch(() => undefined);
      await page.waitForFunction(() => document.body.innerText.includes('今天先做') || document.body.innerText.includes('今天没有待处理'));
      assert.equal(await page.getByText('登录移动工作台').count(), 0);
      assert.equal(await page.locator('.manager-p0-nav button').count(), 4);
      await page.getByRole('button', { name: /巡检照片/ }).click();
      await page.locator('.manager-p0-area').first().waitFor();
      await page.goBack({ waitUntil: 'commit' }).catch(() => undefined);
      await page.waitForFunction(() => document.body.innerText.includes('今天先做') || document.body.innerText.includes('今天没有待处理'));
      assert.equal(await page.getByText('登录移动工作台').count(), 0);
    });

    await check('team-overview', async () => {
      await start('normal'); await loaded(); await tab('我的');
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

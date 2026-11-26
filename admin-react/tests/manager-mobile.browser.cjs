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
  await page.screenshot({ path: path.join(out, file), fullPage: false, animations: 'disabled',
    style: '[data-fixture-controls], .ant-message { display: none !important; }' });
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

    await check('independent-recording-page-save-replay-history', async () => {
      await start('recording'); await loaded();
      await page.getByRole('button', { name: /晨会录音/ }).click();
      await page.waitForURL('**/store/recordings');
      await page.getByRole('heading', { name: '晨会录音' }).waitFor();
      assert.equal(await page.locator('.manager-p0-area, .manager-p0-nav, .manager-home-orders').count(), 0);
      assert.equal(await page.getByRole('button', { name: /发券|核销|提交今日巡检/ }).count(), 0);
      await noOverflow(); await shot('recording-page');
      await context.grantPermissions([], { origin });
      await page.getByRole('button', { name: '开始录音' }).click();
      await page.getByText('无法使用麦克风，请允许麦克风权限后重试。').waitFor();
      await context.grantPermissions(['microphone'], { origin });
      await page.getByRole('button', { name: '开始录音' }).click();
      await page.getByRole('button', { name: '结束并保存' }).waitFor();
      await page.waitForFunction(() => document.querySelector('.manager-p0-recording strong')?.textContent === '00:01');
      await page.getByRole('button', { name: '结束并保存' }).click();
      await page.getByRole('button', { name: '重试保存' }).click();
      await page.getByText('录音已保存', { exact: true }).waitFor();
      assert.equal(await page.locator('.manager-recording-item').count(), 1, 'A lost save receipt must not duplicate the recording');
      await page.getByRole('button', { name: '载入录音' }).click();
      await page.waitForFunction(() => document.querySelector('audio')?.src.startsWith('blob:'));
      await page.locator('audio').evaluate(a => a.play());
      await page.getByRole('button', { name: '重新转写' }).click();
      await page.getByText('查看文字稿').click();
      await page.getByText('晨会测试文字稿').waitFor();
      await page.getByLabel('录音日期').fill('2026-11-08');
      await page.getByText('当天没有录音').waitFor();
      assert.equal(await page.getByRole('button', { name: '开始录音' }).count(), 0);
      await page.getByRole('button', { name: '回到今天' }).click();
      await page.getByText('查看文字稿').waitFor();
      await page.getByRole('button', { name: '返回', exact: true }).click();
      await loaded();
      await page.getByRole('button', { name: /录音记录/ }).click();
      await page.getByRole('heading', { name: '晨会录音' }).waitFor();
      await page.reload();
      await page.waitForURL('**/store/login');
      assert.equal(await page.getByRole('heading', { name: '晨会录音' }).count(), 0);
      await start('recording', 375, '/technician/store/recordings');
      await page.getByRole('heading', { name: '晨会录音' }).waitFor();
      await context.clearPermissions();
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
      await area.getByRole('button', { name: '煮药区照片与审核' }).click();
      const album = page.getByRole('region', { name: '煮药区已拍照片' });
      await album.getByRole('img', { name: '煮药区照片 3' }).waitFor();
      assert.equal(await album.getByRole('img', { name: /煮药区照片/ }).count(), 3);
      page.once('dialog', dialog => dialog.accept());
      await album.getByRole('button', { name: '更换煮药区第 2 张' }).click();
      await shoot();
      await album.getByRole('button', { name: '更换煮药区第 2 张' }).waitFor();
      await page.waitForFunction(() => !document.querySelector('.manager-p0-area[aria-label="煮药区"] button')?.disabled);
      assert.equal(await page.getByRole('progressbar', { name: '已完成拍摄点' }).getAttribute('value'), '4');
      await noOverflow();
    });

    await check('huafu-four-independent-spa-rooms', async () => {
      await start('huafu-inspection'); await loaded();
      await page.getByRole('button', { name: /巡检照片/ }).click();
      const rooms = page.getByRole('region', { name: 'SPA 房', exact: true });
      await rooms.waitFor();
      assert.equal(await page.locator('.manager-p0-area').count(), 12);
      assert.deepEqual(await rooms.locator('.inspection-point strong').allTextContents(), ['半夏', '忍冬', '杜若', '青黛']);
      await shot('huafu-inspection-overview');
      const filters = page.getByRole('group', { name: '筛选拍摄点' });
      await filters.getByRole('button', { name: /待拍/ }).click();
      assert.equal(await page.locator('.inspection-point').count(), 9);
      await filters.getByRole('button', { name: /已拍/ }).click();
      assert.equal(await page.locator('.inspection-point').count(), 3);
      await filters.getByRole('button', { name: /全部/ }).click();
      await context.grantPermissions(['camera'], { origin });
      await rooms.locator('[aria-label="杜若"]').getByRole('button', { name: '现场拍照' }).click();
      await page.getByRole('dialog', { name: 'SPA 房·杜若 · 现场拍照' }).getByRole('button', { name: '拍摄并保存' }).click();
      await rooms.getByText('已拍 1/4 间').waitFor();
      await rooms.locator('[aria-label="青黛"]').getByText('待拍', { exact: true }).waitFor();
      await rooms.locator('[aria-label="杜若"]').getByText('1 张', { exact: true }).waitFor();
      await filters.getByRole('button', { name: /已拍/ }).click();
      await rooms.getByRole('button', { name: '杜若照片与审核' }).click();
      await rooms.getByRole('region', { name: '杜若已拍照片' }).waitFor();
      await rooms.getByRole('button', { name: '收起杜若照片' }).click();
      await filters.getByRole('button', { name: /待拍/ }).click();
      assert.equal(await page.locator('.inspection-point').count(), 8);
      await filters.getByRole('button', { name: /全部/ }).click();
      await page.setViewportSize({ width: 320, height: 740 }); await noOverflow();
      for (const btn of await rooms.locator('.inspection-point button').all()) {
        const box = await btn.boundingBox(); assert.ok(box && box.width >= 44 && box.height >= 44);
      }
      await page.setViewportSize({ width: 375, height: 812 });
      await rooms.scrollIntoViewIfNeeded(); await noOverflow(); await shot('huafu-spa-rooms');
      await start('normal'); await loaded();
      await page.getByRole('button', { name: /巡检照片/ }).click();
      await page.locator('.manager-p0-area').first().waitFor();
      assert.equal(await rooms.count(), 0);
      assert.equal(await page.locator('.manager-p0-area').count(), 6);
    });

    await check('inspection-ai-automatic-current-and-past-photos', async () => {
      await start('inspection-ai'); await loaded();
      await page.getByRole('button', { name: /巡检照片/ }).click();
      await page.getByRole('button', { name: '卫生间照片与审核' }).click();
      const area = page.getByRole('region', { name: '卫生间已拍照片' });
      await area.getByText('等待自动审核').waitFor();
      assert.equal(await page.getByRole('button', { name: /审核这张照片|重试初审|送审/ }).count(), 0);
      await area.getByText('AI 审核 · 需整改').waitFor({ timeout: 26000 });
      await area.getByText('洗手台左侧 · 台面散落纸巾').waitFor();
      await area.getByText('清走纸巾后擦净台面').waitFor();
      await noOverflow(); await shot('inspection-automatic-result');
      assert.equal(await area.getByRole('button', { name: /保存更正|结果有误/ }).count(), 0);
      const tasks = page.getByRole('region', { name: '本店待处理巡检' });
      await tasks.getByText('卫生间 · 需整改').waitFor();
      assert.equal(await area.getByRole('button', { name: '更换卫生间第 1 张' }).count(), 0);
      await context.grantPermissions(['camera'], { origin });
      await tasks.getByRole('button', { name: '现场复拍' }).click();
      await page.getByRole('button', { name: '拍摄并保存' }).click();
      await tasks.getByText('卫生间 · 复查中').waitFor();
      await area.getByText('复查通过 · 已结案').waitFor({ timeout: 26000 });
      assert.equal(await tasks.count(), 0);
      await area.getByText('AI 审核 · 需整改').waitFor();
      await noOverflow(); await shot('inspection-original-and-verified-recapture');
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

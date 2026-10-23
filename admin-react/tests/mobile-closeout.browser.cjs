'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.MANAGER_TEST_PLAYWRIGHT || 'playwright');
const origin = process.env.CLOSEOUT_TEST_ORIGIN || 'http://127.0.0.1:18420';
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(origin)) throw Error('Loopback fixture only');
const out = path.resolve(process.env.CLOSEOUT_TEST_OUTPUT || 'output/playwright/mobile-closeout');
const report = { passed: false, productionWrites: 0, cases: [], unexpectedRequests: [], pageErrors: [] };
let browser;
async function main() {
  await fs.mkdir(out, { recursive: true });
  browser = await chromium.launch({ headless: true, channel: process.env.CLOSEOUT_BROWSER_CHANNEL || undefined, args: ['--disable-background-networking'] });
  report.browserVersion = browser.version();
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: 'block' });
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin || url.pathname.startsWith('/api/')) {
      report.unexpectedRequests.push(url.origin + url.pathname); return route.abort();
    }
    return route.continue();
  });
  const page = await context.newPage();
  page.on('pageerror', error => report.pageErrors.push(error.message));
  const open = async mode => page.goto(origin + '/tests/mobile-closeout.html?mode=' + mode);
  const check = async (name, run) => {
    if (process.env.CLOSEOUT_CASE_FILTER && !new RegExp(process.env.CLOSEOUT_CASE_FILTER).test(name)) return;
    await run(); report.cases.push(name);
  };
  const waitFor = check => page.waitForFunction(check);
  await check('acknowledge retains unresolved task and prevents duplicate clicks', async () => {
    await open('manager');
    const button = page.getByRole('button', { name: '确认知悉', exact: true });
    await button.waitFor();
    await button.evaluate(node => { node.click(); node.click(); });
    await page.getByText('已知悉 · 待处理', { exact: true }).waitFor();
    assert.equal(await page.evaluate(() => window.closeoutStats.ack), 1);
    assert.equal(await page.getByText('INTERNAL-STATE').count(), 0);
    assert.equal(await page.getByRole('button', { name: '确认知悉', exact: true }).count(), 0);
    await page.getByRole('button', { name: '查看本店服务单', exact: true }).click();
    await page.getByText('全部服务单', { exact: true }).waitFor();
    await page.screenshot({ path: path.join(out, 'manager.png') });
  });
  await check('return refresh clears completed record reminder without writing or resolving exception', async () => {
    await page.getByText('1 次服务待填写', { exact: true }).waitFor();
    await page.getByRole('button', { name: '模拟返回并已补填' }).click();
    await page.getByText('1 次服务待填写', { exact: true }).waitFor({ state: 'hidden' });
    await page.getByText('已知悉 · 待处理', { exact: true }).waitFor();
    assert.equal(await page.evaluate(() => window.closeoutStats.ack), 1);
  });
  await check('acknowledge network failure remains retryable', async () => {
    await open('ack-error');
    await page.getByRole('button', { name: '确认知悉', exact: true }).click();
    await page.getByText('未能确认知悉，请重试；事项仍保留在列表中。', { exact: true }).waitFor();
    await page.getByRole('button', { name: '确认知悉', exact: true }).click();
    await page.getByText('已知悉 · 待处理', { exact: true }).waitFor();
  });
  await check('load failure is not presented as an empty successful queue', async () => {
    await open('load-error');
    await page.getByText('待处理事项加载失败，请重试', { exact: true }).waitFor();
    assert.equal(await page.getByText('当前没有待处理', { exact: true }).count(), 0);
  });
  await check('late response after identity change never restores previous tasks', async () => {
    await open('late');
    await page.getByText('正在加载待处理', { exact: true }).waitFor();
    await page.getByRole('button', { name: '切换身份并释放旧响应' }).click();
    await page.getByText('身份已切换', { exact: true }).waitFor();
    assert.equal(await page.getByText('合成技师', { exact: true }).count(), 0);
  });
  await check('history pending filter opens existing record editor and save clears task', async () => {
    await open('history');
    await page.getByRole('checkbox', { name: '只看待填写' }).check();
    await waitFor(() => window.closeoutStats.filter === 'pending');
    await page.getByRole('button', { name: '补填服务记录' }).click();
    await page.getByRole('button', { name: '本次没有新情况', exact: true }).click();
    await page.getByText('当前筛选下没有待填写的服务记录', { exact: true }).waitFor();
    assert.equal(await page.evaluate(() => window.closeoutStats.saves), 1);
  });
  await check('failed record save preserves editor and task for retry', async () => {
    await open('save-error');
    await page.getByRole('checkbox', { name: '只看待填写' }).check();
    await page.getByRole('button', { name: '补填服务记录' }).click();
    await page.getByRole('button', { name: '本次没有新情况', exact: true }).click();
    await page.getByText('保存失败，内容已保留，请重试。', { exact: true }).waitFor();
    assert.equal(await page.evaluate(() => window.closeoutStats.pending), 1);
    await page.getByRole('button', { name: '本次没有新情况', exact: true }).click();
    await page.getByText('当前筛选下没有待填写的服务记录', { exact: true }).waitFor();
  });
  assert.deepEqual(report.unexpectedRequests, []);
  assert.deepEqual(report.pageErrors, []);
  assert.equal(await page.evaluate(() => window.closeoutStats.unexpected), 0);
  report.passed = true;
}
main().catch(error => { report.failure = error.message; process.exitCode = 1; }).finally(async () => {
  if (browser) await browser.close();
  await fs.writeFile(path.join(out, 'report.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
});

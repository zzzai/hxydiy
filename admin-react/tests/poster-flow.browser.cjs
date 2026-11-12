const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require('../../output/poster-preview/tools/node_modules/playwright');
const output = path.resolve('../output/poster-preview');
async function main() {
  const browser = await chromium.launch({ channel: 'chromium', args: ['--no-sandbox', '--disable-background-networking'] });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: 'block' });
  const report = { passed: false, cases: [], pageErrors: [], unexpectedRequests: [], productionWrites: 0, realSmsSent: 0 };
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin !== 'http://127.0.0.1:18444' || url.pathname.startsWith('/api/')) {
      report.unexpectedRequests.push(url.pathname);
      return route.abort();
    }
    return route.continue();
  });
  const page = await context.newPage();
  page.on('pageerror', error => report.pageErrors.push(error.message));
  try {
    await page.goto('http://127.0.0.1:18444/flow.html');
    await page.getByRole('button', { name: '登录并领取', exact: true }).waitFor();
    await page.screenshot({ path: path.join(output, 'claim-login.png'), fullPage: true, animations: 'disabled' });
    assert.equal((await page.evaluate(() => window.posterFlowTest.read())).claims, 0);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.getByPlaceholder('请输入本人手机号').fill('13800138000');
    await page.getByRole('button', { name: '获取验证码', exact: true }).click();
    await page.getByRole('textbox', { name: '短信验证码' }).fill('123456');
    await page.getByRole('button', { name: '登录并领取', exact: true }).click();
    await page.getByText('已领取，已绑定本人', { exact: true }).waitFor();
    assert.equal((await page.evaluate(() => window.posterFlowTest.read())).claims, 1);
    report.cases.push('Opening is read-only; explicit phone login and claim binds the first recipient');
    await page.getByRole('button', { name: '到店出示核销码' }).click();
    await page.getByText(/请本人现场出示/).waitFor();
    await page.screenshot({ path: path.join(output, 'claim-owned.png'), fullPage: true, animations: 'disabled' });
    await page.getByRole('button', { name: '顾客甲', exact: true }).click();
    await page.getByText('已领取，已绑定本人', { exact: true }).waitFor();
    assert.equal((await page.evaluate(() => window.posterFlowTest.read())).claims, 1);
    report.cases.push('The owner can reopen without issuing another coupon');
    await page.getByRole('button', { name: '顾客乙', exact: true }).click();
    await page.getByText('这张券已被领取', { exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: '到店出示核销码' }).count(), 0);
    assert.equal(await page.locator('.poster-claim-page').getByText(/138.*8000/).count(), 0);
    await page.screenshot({ path: path.join(output, 'claim-taken.png'), fullPage: true, animations: 'disabled' });
    report.cases.push('A different recipient sees claimed, with no owner details or redemption QR');
    await page.getByRole('button', { name: '店长扫码核销', exact: true }).click();
    await page.getByText('可核销', { exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: '确认核销', exact: true }).isDisabled(), true);
    assert.equal((await page.evaluate(() => window.posterFlowTest.read())).used, false);
    await page.getByRole('checkbox', { name: '已核对顾客本人现场出示的券码及账户信息' }).check();
    await page.screenshot({ path: path.join(output, 'manager-redeem.png'), fullPage: true, animations: 'disabled' });
    await page.getByRole('button', { name: '确认核销', exact: true }).click();
    await page.getByText(/已核销，券已失效/).waitFor();
    assert.equal((await page.evaluate(() => window.posterFlowTest.read())).redeems, 1);
    await page.getByRole('button', { name: '顾客甲', exact: true }).click();
    await page.getByText('这张券已核销', { exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: '到店出示核销码' }).count(), 0);
    await page.screenshot({ path: path.join(output, 'claim-used.png'), fullPage: true, animations: 'disabled' });
    report.cases.push('Manager scan only previews; explicit holder check and confirm invalidates the coupon');
    assert.deepEqual(report.pageErrors, []);
    assert.deepEqual(report.unexpectedRequests, []);
    report.passed = true;
  } catch (error) {
    await page.screenshot({ path: path.join(output, 'flow-failure.png'), fullPage: true });
    await fs.writeFile(path.join(output, 'flow-failure-dom.txt'), await page.locator('body').innerText());
    throw error;
  } finally {
    await fs.writeFile(path.join(output, 'flow-browser-report.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report)); await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });

// Isolated real identity/consent API with synthetic source; never read real reports.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const fixture = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
assert.equal(fixture.synthetic, true);
assert.equal(new URL(fixture.apiBase).hostname, '127.0.0.1');
const out = path.resolve('output/playwright/tcm-direct-report-04');
fs.mkdirSync(out, { recursive: true });
(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  const results = [];
  try {
    for (const width of [375, 390]) {
      for (const account of ['full', 'other']) {
        const context = await browser.newContext({ viewport: { width, height: 844 } });
        const auth = fixture.accounts[account];
        const control = async (action, rest = {}) => {
          const response = await context.request.post(fixture.apiBase + '/synthetic-test/control', { data: { account, action, ...rest } });
          assert.equal(response.status(), 200);
        };
        await control('reset');
        await context.addInitScript(value => localStorage.setItem('hxy_diy_customer_auth', JSON.stringify(value)), auth);
        const original = [];
        await context.route('https://yk.qianmaitcm.com/print_smart_healthcare/**', async route => {
          original.push({ url: route.request().url(), referer: route.request().headers().referer });
          await route.fulfill({ contentType: 'text/html', body: '<title>Synthetic original</title><p>Synthetic full report</p>' });
        });
        const page = await context.newPage();
        const requests = [];
        page.on('request', req => requests.push(req.url()));
        const profile = async () => {
          await page.goto(fixture.url);
          await page.locator('.miniapp-profile-entry').click();
          await page.locator('.profile-pending-task').waitFor();
          await page.locator('.toast').waitFor({ state: 'hidden' });
          await page.waitForFunction(() => [...document.querySelectorAll('[role="dialog"]')].every(el => Number(getComputedStyle(el).opacity) >= 0.99));
        };
        await profile();
        const gap = await page.evaluate(() => document.querySelector('.membership-banner').getBoundingClientRect().top - document.querySelector('.profile-pending-task').getBoundingClientRect().bottom);
        assert.equal(gap, 16);
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await page.screenshot({ path: path.join(out, `${width}-${account}-profile-gap.png`) });
        const enter = async () => {
          await page.locator('.profile-pending-task').click();
          const consent = page.getByRole('checkbox');
          await page.waitForFunction(() => document.querySelector('.my-reports-consent') || document.querySelector('.my-reports-list') || document.querySelector('.my-reports-error'));
          await page.waitForFunction(() => !document.querySelector('.my-reports-loading'));
          if (await consent.count()) {
            await consent.check();
            await page.getByRole('button', { name: '同意并查看', exact: true }).click();
          }
          await page.locator('.my-reports-row').first().waitFor();
        };
        await enter();
        await page.screenshot({ path: path.join(out, `${width}-${account}-list.png`) });
        assert.equal(original.length, 0);
        const previewNodes = [];
        await page.evaluate(() => new MutationObserver(() => {
          if (document.querySelector('.my-reports-detail')) console.error('UNEXPECTED_REPORT_PREVIEW');
        }).observe(document.body, { subtree: true, childList: true }));
        page.on('console', msg => { if (msg.text() === 'UNEXPECTED_REPORT_PREVIEW') previewNodes.push(true); });
        await page.locator('.my-reports-row').first().click();
        await page.waitForURL(fixture.originalUrls[account]);
        assert.equal(original.at(-1).referer, undefined);
        assert.equal(previewNodes.length, 0);
        await page.screenshot({ path: path.join(out, `${width}-${account}-original.png`) });
        assert(!requests.some(url => /send-code|login-phone/.test(url)));
        await profile(); await enter();
        await control('null-link');
        await page.locator('.my-reports-row').first().click();
        await page.getByText('完整报告地址暂不可用，请稍后重试或联系门店。', { exact: true }).waitFor();
        assert.equal(await page.locator('.my-reports-detail').count(), 0);
        await page.screenshot({ path: path.join(out, `${width}-${account}-missing-link.png`) });
        await control('detail-unavailable', { enabled: true });
        await page.locator('.my-reports-row').first().click();
        await page.getByText('检测报告服务暂时不可用，请稍后再试。', { exact: true }).waitFor();
        await control('detail-unavailable', { enabled: false });
        await page.getByRole('button', { name: '撤回授权', exact: true }).click();
        await page.getByRole('checkbox').waitFor();
        assert.equal(await page.locator('.my-reports-row').count(), 0);
        assert.equal(original.length, 1);
        const detailPattern = '**/api/v1/me/tcm-reports/SYNTHETIC-R-*';
        await profile(); await enter();
        await page.route(detailPattern, route => route.abort('failed'));
        await page.locator('.my-reports-row').first().click();
        await page.getByText('网络连接失败，请检查网络后重试。', { exact: true }).waitFor();
        assert.equal(original.length, 1);
        await page.unroute(detailPattern);
        for (const status of [401, 403]) {
          await profile(); await enter();
          await page.route(detailPattern, route => route.fulfill({ status, json: { detail: { code: status === 401 ? 'AUTH_REQUIRED' : 'TCM_CONSENT_REQUIRED', message: 'Synthetic access denied' } } }));
          await page.locator('.my-reports-row').first().click();
          await page.getByRole('alert').waitFor();
          assert.equal(await page.locator('.my-reports-row').count(), 0);
          assert.equal(original.length, 1);
          assert.equal(await page.getByRole('button', { name: status === 401 ? '重新登录' : '同意并查看', exact: true }).count(), 1);
          await page.unroute(detailPattern);
        }
        await control('reset');
        await profile(); await enter();
        let received;
        const pending = new Promise(resolve => { received = resolve; });
        await page.route(detailPattern, async route => {
          const response = await route.fetch(); received();
          await new Promise(resolve => setTimeout(resolve, 650));
          await route.fulfill({ response }).catch(() => {});
        });
        await page.locator('.my-reports-row').first().click();
        await pending;
        await page.getByRole('button', { name: '撤回授权', exact: true }).click();
        await page.getByRole('checkbox').waitFor();
        await page.waitForTimeout(800);
        assert.equal(original.length, 1);
        assert.equal(await page.locator('.my-reports-row').count(), 0);
        await page.unroute(detailPattern);
        await context.route('**/api/v1/auth/h5/me', async route => {
          const response = await route.fetch(); const user = await response.json();
          await route.fulfill({ response, json: { ...user, is_member: true, member_type: 'annual' } });
        });
        await context.addInitScript(value => localStorage.setItem('hxy_diy_customer_auth', JSON.stringify({ ...value, user: { ...value.user, is_member: true, member_type: 'annual' } })), auth);
        await profile();
        assert.equal(await page.locator('.membership-banner').count(), 0);
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await page.screenshot({ path: path.join(out, `${width}-${account}-member-profile.png`) });
        results.push({ width, account, gap, direct: true, preview: false, noRepeatedOtp: true, missingLink: true, sourceFailure: true, networkFailure: true, withdrawn: true, denied401403: true, lateResponseAfterWithdrawal: true, memberBannerHidden: true });
        await context.close();
      }
    }
    fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify({ productionWrites: false, environment: 'isolated localhost API; synthetic external source and member visibility response', results }, null, 2));
    console.log(JSON.stringify({ passed: results.length, report: path.join(out, 'result.json') }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

// Real isolated report API and consent database; only the external source is synthetic.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const fixture = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
assert.equal(fixture.synthetic, true);
assert.equal(new URL(fixture.apiBase).hostname, '127.0.0.1');
const out = path.resolve(process.argv[3] || 'output/playwright/tcm-original-report-02');
fs.mkdirSync(out, { recursive: true });

(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  const results = [];
  try {
    for (const width of [375, 390]) {
      for (const account of ['full', 'other', 'empty']) {
        const context = await browser.newContext({ viewport: { width, height: 844 } });
        const auth = fixture.accounts[account];
        const headers = { Authorization: `Bearer ${auth.token}` };
        const control = async (action, values = {}) => {
          const response = await context.request.post(`${fixture.apiBase}/synthetic-test/control`, { data: { action, account, ...values } });
          assert.equal(response.status(), 200);
          return response.json();
        };
        await control('reset');
        const consentResponse = await context.request.get(`${fixture.apiBase}/api/v1/me/tcm-report-consent`, { headers });
        assert.equal(consentResponse.status(), 200);
        const consent = await consentResponse.json();
        assert.equal(consent.consented, false);
        await context.addInitScript(value => localStorage.setItem('hxy_diy_customer_auth', JSON.stringify(value)), auth);
        const page = await context.newPage();
        const requests = [], errors = [], originalRequests = [];
        page.on('request', request => requests.push({ url: request.url(), method: request.method(), body: request.postData() || '' }));
        page.on('pageerror', error => errors.push(error.message));
        await context.route('https://yk.qianmaitcm.com/print_smart_healthcare/**', async route => {
          originalRequests.push({ url: route.request().url(), referer: route.request().headers().referer });
          await route.fulfill({ contentType: 'text/html', body: '<title>Synthetic original report</title><p>Synthetic report fixture</p>' });
        });
        await page.goto(fixture.url);
        await page.locator('.project-card').first().waitFor();
        requests.length = 0;
        await page.locator('.miniapp-profile-entry').click();
        assert(!requests.some(r => r.url.includes('tcm-report')));
        await page.locator('.profile-pending-task').click();
        await page.getByRole('checkbox').waitFor();
        assert.equal(await page.getByRole('checkbox').isChecked(), false);
        assert(await page.getByText(consent.notice, { exact: true }).isVisible());
        assert(!requests.some(r => /\/me\/tcm-reports(?:\?|\/|$)/.test(r.url)));
        await page.locator('.toast').waitFor({ state: 'hidden' });
        await page.screenshot({ path: path.join(out, `${width}-${account}-consent.png`) });
        await page.getByRole('checkbox').check();
        await page.getByRole('button', { name: '同意并查看', exact: true }).click();
        await page.getByRole('button', { name: '刷新报告', exact: true }).waitFor();
        await page.waitForFunction(() => !document.querySelector('.my-reports-loading'));
        const grant = requests.find(r => r.method === 'POST' && r.url.includes('/me/tcm-report-consent'));
        assert.equal(JSON.parse(grant.body).version, consent.version);
        assert.equal(JSON.parse(grant.body).accepted, true);
        assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem('hxy_diy_customer_auth')).token), auth.token);
        const layout = async state => {
          assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
          await page.screenshot({ path: path.join(out, `${width}-${account}-${state}.png`) });
        };
        const rowCount = () => page.locator('.my-reports-row').count();
        const listReads = () => requests.filter(r => r.method === 'GET' && /\/me\/tcm-reports\?/.test(r.url)).length;
        if (account === 'empty') {
          await page.getByText('还没做过检测？到店后可联系前台，安排体质检测。', { exact: true }).waitFor();
          await layout('empty');
        } else {
          await page.locator('.my-reports-row').first().waitFor();
          await layout('list');
          assert.equal(originalRequests.length, 0);
          await page.locator('.my-reports-row').first().click();
          const link = page.getByRole('link', { name: '打开完整检测报告', exact: true });
          await link.waitFor();
          assert.equal(await link.getAttribute('href'), fixture.originalUrls[account]);
          assert.equal(await link.getAttribute('target'), '_blank');
          assert.equal(await link.getAttribute('rel'), 'noopener noreferrer');
          assert.equal(originalRequests.length, 0);
          await layout('original');
          const popupPromise = context.waitForEvent('page');
          await link.click();
          const popup = await popupPromise;
          await popup.waitForLoadState();
          assert.equal(popup.url(), fixture.originalUrls[account]);
          assert.equal(await popup.evaluate(() => window.opener), null);
          assert.equal(originalRequests.at(-1).referer, undefined);
          await popup.close();
          await control('append');
          await page.getByRole('button', { name: '查看报告列表', exact: true }).click();
          await page.waitForFunction(() => document.querySelectorAll('.my-reports-row').length === 2);
          await control('append');
          await page.getByRole('button', { name: '刷新报告', exact: true }).click();
          await page.waitForFunction(() => document.querySelectorAll('.my-reports-row').length === 3);
          await control('append');
          const reads = listReads();
          await page.evaluate(() => { window.dispatchEvent(new Event('focus')); document.dispatchEvent(new Event('visibilitychange')); });
          await page.waitForFunction(() => document.querySelectorAll('.my-reports-row').length === 4);
          await page.waitForTimeout(450);
          assert.equal(listReads() - reads, 1);
          const hiddenReads = listReads();
          await page.evaluate(() => {
            Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
            window.dispatchEvent(new Event('focus')); document.dispatchEvent(new Event('visibilitychange'));
          });
          await page.waitForTimeout(350);
          assert.equal(listReads(), hiddenReads);
          await page.evaluate(() => { delete document.visibilityState; });
          await control('unavailable', { enabled: true });
          await page.getByRole('button', { name: '刷新报告', exact: true }).click();
          await page.getByRole('alert').waitFor();
          assert.equal(await rowCount(), 4);
          await layout('refresh-error');
          await control('unavailable', { enabled: false });
          await page.getByRole('button', { name: '重新加载', exact: true }).click();
          await page.getByRole('alert').waitFor({ state: 'hidden' });
          await control('detail-unavailable', { enabled: true });
          await page.locator('.my-reports-row').first().click();
          await page.getByRole('alert').waitFor();
          await control('detail-unavailable', { enabled: false });
          await page.getByRole('button', { name: '重新加载', exact: true }).click();
          await page.getByRole('alert').waitFor({ state: 'hidden' });
          assert.equal(await page.locator('.my-reports-detail').count(), 0);
          assert.equal(await rowCount(), 4);
          await control('null-link');
          await page.locator('.my-reports-row').first().click();
          await page.getByText('完整报告暂不可用，以下为已有原始结果。', { exact: true }).waitFor();
          assert.equal(await page.getByRole('link', { name: '打开完整检测报告' }).count(), 0);
          assert((await page.locator('.my-reports-detail').innerText()).includes('42'));
          await layout('unavailable-link');
          await page.getByRole('button', { name: '查看报告列表', exact: true }).click();
          await page.waitForFunction(() => !document.querySelector('.my-reports-loading'));
          if (width === 390 && account === 'full') {
            await control('deny-list', { enabled: true });
            await page.getByRole('button', { name: '刷新报告', exact: true }).click();
            await page.getByRole('checkbox').waitFor();
            assert.equal(await page.getByRole('checkbox').isChecked(), false);
            assert.equal(await rowCount(), 0);
            assert.equal(await page.getByRole('button', { name: '刷新报告', exact: true }).count(), 0);
            await control('deny-list', { enabled: false });
            await page.getByRole('checkbox').check();
            await page.getByRole('button', { name: '同意并查看', exact: true }).click();
            await page.waitForFunction(() => !document.querySelector('.my-reports-loading'));
            await control('expire-login', { enabled: true });
            await page.getByRole('button', { name: '刷新报告', exact: true }).click();
            await page.getByRole('button', { name: '重新登录', exact: true }).waitFor();
            assert.equal(await rowCount(), 0);
            assert.equal(await page.getByRole('checkbox').count(), 0);
            assert.equal(await page.getByRole('button', { name: '刷新报告', exact: true }).count(), 0);
            await control('expire-login', { enabled: false });
            await page.getByRole('button', { name: '重新加载', exact: true }).count().then(count => assert.equal(count, 0));
            await page.getByRole('button', { name: '重新登录', exact: true }).click();
            await page.evaluate(value => localStorage.setItem('hxy_diy_customer_auth', JSON.stringify(value)), auth);
            await page.goto(fixture.url);
            await page.locator('.miniapp-profile-entry').click();
            await page.locator('.profile-pending-task').click();
            await page.getByRole('button', { name: '刷新报告', exact: true }).waitFor();
            await page.waitForFunction(() => !document.querySelector('.my-reports-loading'));
          }
        }
        // Delay a real list response, then withdraw: abort must prevent restoration.
        let received;
        const pending = new Promise(resolve => { received = resolve; });
        const listPattern = '**/api/v1/me/tcm-reports?*';
        await page.route(listPattern, async route => {
          const response = await route.fetch(); received();
          await new Promise(resolve => setTimeout(resolve, 650));
          await route.fulfill({ response }).catch(() => {});
        });
        await page.getByRole('button', { name: '刷新报告', exact: true }).click();
        await pending;
        await page.getByRole('button', { name: '撤回授权', exact: true }).click();
        await page.getByRole('checkbox').waitFor();
        await page.waitForTimeout(800);
        assert.equal(await rowCount(), 0);
        assert.equal(await page.locator('.my-reports-original').count(), 0);
        await page.unroute(listPattern);
        await page.getByRole('checkbox').check();
        await page.getByRole('button', { name: '同意并查看', exact: true }).click();
        await page.waitForFunction(() => !document.querySelector('.my-reports-loading'));
        // Delayed responses must also stay discarded after logout or changing number.
        for (const action of ['change-phone', 'logout']) {
          let receivedLate;
          const pendingLate = new Promise(resolve => { receivedLate = resolve; });
          await page.route(listPattern, async route => {
            const response = await route.fetch(); receivedLate();
            await new Promise(resolve => setTimeout(resolve, 650));
            await route.fulfill({ response }).catch(() => {});
          });
          await page.getByRole('button', { name: '刷新报告', exact: true }).click();
          await pendingLate;
          if (action === 'logout') await page.getByRole('button', { name: '退出登录', exact: true }).click();
          else {
            // Changing the number remains available to cancel the current report view.
            await page.getByRole('button', { name: '重新验证其他号码', exact: true }).click();
          }
          await page.waitForTimeout(800);
          assert.equal(await page.locator('.my-reports').count(), 0);
          assert.equal(await page.evaluate(() => localStorage.getItem('hxy_diy_customer_auth')), null);
          await page.unroute(listPattern);
          if (action === 'change-phone') {
            await page.evaluate(value => localStorage.setItem('hxy_diy_customer_auth', JSON.stringify(value)), auth);
            await page.goto(fixture.url);
            await page.locator('.miniapp-profile-entry').click();
            await page.locator('.profile-pending-task').click();
            await page.getByRole('button', { name: '刷新报告', exact: true }).waitFor();
            await page.waitForFunction(() => !document.querySelector('.my-reports-loading'));
          }
        }
        const stored = await page.evaluate(() => JSON.stringify({ local: localStorage, session: sessionStorage }));
        assert(!stored.includes('yk.qianmaitcm.com') && !stored.includes('SYNTHETIC-R'));
        assert(!requests.some(r => /send-code|\/login(?:\?|$)/.test(r.url)));
        assert(!requests.some(r => r.method !== 'GET' && /entry-sessions|occupancies|selection-sessions|orders/.test(r.url)));
        assert(!requests.some(r => /tracking|events/.test(r.url) && /yk\.qianmaitcm\.com|SYNTHETIC-R/.test(r.body)));
        assert.deepEqual(errors, []);
        results.push({ width, account, explicitUpgrade: true, sameLogin: true, ownerLink: account === 'empty' ? null : true, refreshPreserves: account === 'empty' ? null : true, focusDeduplicated: account === 'empty' ? null : true, delayedResultsDiscarded: true, noHealthStorageOrTracking: true, noSelectionWrites: true });
        await context.close();
      }
    }
    fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify({ realIsolatedApi: true, syntheticSourceOnly: true, results }, null, 2));
    console.log(JSON.stringify(results));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

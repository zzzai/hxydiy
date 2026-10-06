// Synthetic backend fixture only. Report/auth/consent responses remain real HTTP.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const fixture = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
assert.equal(fixture.synthetic, true);
const out = path.resolve(process.argv[3] || 'output/playwright/tcm-report-ui-02');
fs.mkdirSync(out, { recursive: true });

(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  const results = [];
  try {
    for (const width of [375, 390]) {
      for (const account of process.env.REPORT_UI_ACCOUNT ? [process.env.REPORT_UI_ACCOUNT] : ['full', 'empty', 'unavailable']) {
        const context = await browser.newContext({ viewport: { width, height: width === 375 ? 812 : 844 }, reducedMotion: width === 390 ? 'reduce' : 'no-preference' });
        const auth = fixture.accounts[account];
        await context.addInitScript(value => localStorage.setItem('hxy_diy_customer_auth', JSON.stringify(value)), auth);
        const headers = { Authorization: `Bearer ${auth.token}` };
        if (account === 'full') await context.request.delete('http://127.0.0.1:8022/api/v1/me/tcm-report-consent', { headers });
        else await context.request.post('http://127.0.0.1:8022/api/v1/me/tcm-report-consent', { headers, data: { accepted: true, version: 'tcm-report-access-v1' } });
        const page = await context.newPage();
        const requests = [], errors = [];
        page.on('request', request => requests.push({ url: request.url(), method: request.method() }));
        page.on('pageerror', error => errors.push(error.message));
        // Selection-state fixtures do not replace report/auth/consent endpoints.
        await page.route('**/api/v1/entry-sessions', async route => {
          if (width === 375) return route.fulfill({ status: 410, contentType: 'application/json', body: JSON.stringify({ detail: '本次位置已释放' }) });
          const response = await route.fetch();
          assert.equal(response.status(), 200);
          const body = await response.json();
          body.occupancy.hold_expires_at = '2020-01-01T00:00:00Z';
          await route.fulfill({ response, json: body });
        });
        if (width === 390) await page.route('**/api/v1/stores/1/service-position-map*', async route => {
          const response = await route.fetch();
          const body = await response.json();
          for (const position of body.positions) if (position.occupancy) position.occupancy.hold_expires_at = '2020-01-01T00:00:00Z';
          await route.fulfill({ response, json: body });
        });
        await page.goto(fixture.url);
        await page.locator('.status-screen').waitFor();
        requests.length = 0;
        await page.getByRole('button', { name: '我的检测报告', exact: true }).click();
        await page.locator('.my-reports').waitFor();
        const header = page.locator('.profile-page > header');
        const checkLayout = async state => {
          assert.equal(await header.locator('strong').innerText(), '我的检测报告');
          assert.equal(await page.getByRole('button', { name: '返回个人中心', exact: true }).count(), 0);
          assert.equal(await page.locator('.my-reports h2').count(), 0);
          assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
          assert.equal(await page.locator('.my-reports').evaluate(element => getComputedStyle(element).backgroundColor), 'rgb(255, 255, 255)');
          if (width === 390) assert(parseFloat(await page.locator('.my-reports button').first().evaluate(element => getComputedStyle(element).transitionDuration)) <= 0.00001);
          await page.waitForTimeout(200);
          await page.screenshot({ path: path.join(out, `${width}-${state}.png`) });
        };
        const goMy = async () => {
          await header.getByRole('button', { name: '返回我的', exact: true }).click();
          await page.locator('.profile-body').waitFor();
          assert.equal(await header.locator('strong').innerText(), '我的');
          assert.equal(await page.locator('.my-reports').count(), 0);
          assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem('hxy_diy_customer_auth')).token), auth.token);
        };
        if (account === 'full') {
          await page.getByRole('checkbox').waitFor();
          assert(!requests.some(request => /\/tcm-reports(?:\?|\/|$)/.test(request.url)));
          await checkLayout('consent');
          await goMy();
          // Repeated direct status entry must reopen the report, not generic My.
          await header.getByRole('button', { name: '返回', exact: true }).click();
          await page.locator('.profile-page').waitFor({ state: 'hidden' });
          await page.getByRole('button', { name: '我的检测报告', exact: true }).click();
          await page.getByRole('checkbox').check();
          await page.getByRole('button', { name: '同意并查看', exact: true }).click();
          await page.locator('.my-reports-row').waitFor();
          await checkLayout('list');
          await page.locator('.my-reports-row').click();
          await page.getByText('合成测试结果', { exact: true }).waitFor();
          assert((await page.locator('.my-reports-detail').innerText()).includes('42'));
          assert.equal(await page.locator('.my-reports img, .my-reports a, .my-reports progress').count(), 0);
          await checkLayout('detail');
          await goMy();
          await page.locator('.profile-pending-task').click();
          await page.locator('.my-reports-row').waitFor();
          await page.getByRole('button', { name: '撤回授权', exact: true }).click();
          await page.getByRole('checkbox').waitFor();
          assert.equal(await page.locator('.my-reports-detail').count(), 0);
        } else if (account === 'empty') {
          await page.getByText('还没有检测报告', { exact: true }).waitFor();
          await checkLayout('empty');
          await goMy();
          await page.locator('.profile-pending-task').click();
          await page.getByText('还没有检测报告', { exact: true }).waitFor();
        } else {
          await page.getByRole('alert').waitFor();
          await checkLayout('failure');
          assert.equal(await page.getByRole('button', { name: '撤回授权', exact: true }).count(), 1);
          await goMy();
        }
        await page.getByRole('button', { name: /退出登录/ }).click();
        assert.equal(await page.locator('.my-reports').count(), 0);
        assert.equal(await page.evaluate(() => localStorage.getItem('hxy_diy_customer_auth')), null);
        assert(!(await page.evaluate(() => JSON.stringify(localStorage))).includes('合成测试结果'));
        assert(!requests.some(request => /send-code|\/login(?:\?|$)/.test(request.url)));
        assert(!requests.some(request => request.method !== 'GET' && /entry-sessions|occupancies|selection-sessions|orders/.test(request.url)));
        assert.deepEqual(errors, []);
        results.push({ width, account, backToMy: true, existingLoginPreserved: true, noSelectionMutation: true, logoutClears: true, overflow: false, reducedMotion: width === 390 });
        await context.close();
      }
    }
    fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify({ synthetic: true, realReportApi: true, selectionStatusOnlySimulated: true, results }, null, 2));
    console.log(JSON.stringify(results));
  } catch (error) {
    for (const page of browser.contexts().flatMap(context => context.pages())) console.error((await page.locator('body').innerText()).slice(-1800));
    throw error;
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

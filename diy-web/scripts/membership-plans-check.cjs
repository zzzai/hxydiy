const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const fixture = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
assert.equal(fixture.synthetic, true);
assert.equal(new URL(fixture.url).hostname, '127.0.0.1');
const out = path.resolve('output/playwright/customer-membership-plans-03');
fs.mkdirSync(out, { recursive: true });
const clean = text => assert(!/499|泡脚月卡|6\.8\s*折|30\s*天不限次|扫码办理|自动到账|自动免单/.test(text));
(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  const results = [];
  try {
    for (const width of [375, 390]) {
      const context = await browser.newContext({ viewport: { width, height: 844 } });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(fixture.url);
      await page.locator('.project-card').first().waitFor();
      clean(await page.locator('.miniapp-promo-strip').innerText());
      const menu = await page.locator('.project-card').first().innerText();
      await page.locator('.toast').waitFor({ state: 'hidden' });
      await page.screenshot({ path: path.join(out, `${width}-entry.png`) });
      for (const [selector, name, price, validity] of [
        ['.membership-promo.annual', '年度会员权益卡', '99', '一年有效'],
        ['.membership-promo.monthly', '储值权益卡', '500', '余额用完，会员权益失效'],
      ]) {
        await page.locator(selector).click();
        const detail = page.locator('.membership-detail-page');
        await detail.waitFor();
        const text = await detail.innerText(); clean(text);
        assert(text.includes(name) && text.includes(price) && text.includes(validity));
        assert(text.includes('按门店价消费任意主项，买一赠一'));
        assert(text.includes('不高于99元的项目1次'));
        assert(text.includes('买赠与赠品由门店确认'));
        if (price === '500') assert(text.includes('价值29.9元养生茶1盒'));
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        assert(await detail.evaluate(node => node.scrollWidth <= node.clientWidth));
        await page.screenshot({ path: path.join(out, `${width}-${price}-detail.png`) });
        await detail.getByRole('button', { name: '返回菜单', exact: true }).click();
        assert.equal(await page.locator('.project-card').first().innerText(), menu);
      }
      // Synthetic identity/read fixtures exercise retained My/report UI, not production auth.
      const payload = Buffer.from(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 3600 })).toString('base64url');
      const auth = { token: `synthetic.${payload}.synthetic`, user: { ...fixture.accounts.full.user, is_member: false } };
      await context.route('**/api/v1/auth/h5/me', route => route.fulfill({ json: auth.user }));
      await context.route('**/api/v1/coupons', route => route.fulfill({ json: { items: [] } }));
      await context.route('**/api/v1/me/tcm-report-consent', route => route.fulfill({ json: { consented: false, version: 'tcm-report-access-v2-original', notice: 'Synthetic report consent notice' } }));
      await page.evaluate(value => localStorage.setItem('hxy_diy_customer_auth', JSON.stringify(value)), auth);
      await page.goto(fixture.url);
      await page.locator('.miniapp-profile-entry').click();
      await page.locator('.membership-banner').waitFor();
      const banner = await page.locator('.membership-banner').innerText(); clean(banner);
      assert(banner.includes('储值权益卡') && banner.includes('29.9'));
      for (const text of ['出示动态会员码', '到店记录']) assert.equal(await page.getByText(text, { exact: true }).count(), 0);
      await page.locator('.toast').waitFor({ state: 'hidden' });
      await page.screenshot({ path: path.join(out, `${width}-my-banner.png`) });
      await page.locator('.profile-pending-task').filter({ hasText: '我的检测报告' }).click();
      await page.locator('.my-reports-consent').waitFor();
      assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem('hxy_diy_customer_auth')).token), auth.token);
      await page.getByRole('button', { name: '返回我的', exact: true }).click();
      await page.locator('.profile-card').waitFor();
      assert.deepEqual(errors, []);
      results.push({ width, bothDetailsAndReturn: true, newBenefitsComplete: true, noOverflow: true, oldPromosAbsent: true, hiddenFunctionsPreserved: true, loginAndReportPreserved: true, projectTextUnchanged: true });
      await context.close();
    }
    fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify({ synthetic: true, productionWrites: false, results }, null, 2));
    console.log(JSON.stringify(results));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

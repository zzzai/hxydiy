// Real customer UI and local API entry; only identity/history fixtures are synthetic.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const fixture = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const mode = process.argv[3] || 'after';
assert.equal(fixture.synthetic, true);
assert.equal(new URL(fixture.apiBase).hostname, '127.0.0.1');
const out = path.resolve('output/playwright/customer-my-stability-03');
fs.mkdirSync(out, { recursive: true });

(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  const results = [];
  try {
    if (mode === 'late') {
      for (const scenario of ['old-401-new-login', 'old-success-new-login', 'old-401-member-change']) {
        const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
        let activeAuth = fixture.accounts.full;
        let releaseOld, receivedOld;
        const received = new Promise(resolve => { receivedOld = resolve; });
        const release = new Promise(resolve => { releaseOld = resolve; });
        let couponCalls = 0;
        const coupon = name => ({ id: 1, name, coupon_type: 'amount', amount_cents: 1000, percent_off: 0, min_spend_cents: 0, status: 'unused', claimed_at: null, expire_at: null });
        await context.route('**/api/v1/auth/h5/me', route => route.fulfill({ json: activeAuth.user }));
        await context.route('**/api/v1/auth/h5/login', route => route.fulfill({ json: activeAuth }));
        await context.route('**/api/v1/coupons', async route => {
          couponCalls++;
          if (couponCalls === 1) {
            receivedOld(); await release;
            await route.fulfill(scenario.includes('success')
              ? { json: { items: [coupon('Old synthetic account coupon')] } }
              : { status: 401, json: { detail: { code: 'SESSION_REPLACED', message: 'Synthetic old session replaced' } } });
          } else await route.fulfill({ json: { items: [coupon('New synthetic account coupon')] } });
        });
        await context.addInitScript(value => localStorage.setItem('hxy_diy_customer_auth', JSON.stringify(value)), activeAuth);
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.goto(fixture.url);
        await page.locator('.miniapp-profile-entry').click();
        await received;
        if (scenario.includes('member-change')) {
          activeAuth = { ...activeAuth, user: { ...activeAuth.user, is_member: true, member_type: 'annual', member_expire_at: '2027-10-07T00:00:00Z' } };
          await page.evaluate(() => window.dispatchEvent(new Event('focus')));
          await page.getByText('年度权益卡会员', { exact: false }).waitFor();
        } else {
          await page.getByRole('button', { name: '退出登录', exact: true }).click();
          await page.locator('.profile-login').waitFor();
          activeAuth = fixture.accounts.other;
          await page.getByPlaceholder('请输入手机号', { exact: true }).fill(activeAuth.user.phone);
          await page.getByPlaceholder('6 位验证码', { exact: true }).fill('123456');
          await page.locator('.profile-login-submit').click();
          await page.getByText('New synthetic account coupon', { exact: true }).waitFor();
        }
        releaseOld();
        await page.waitForTimeout(400);
        assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem('hxy_diy_customer_auth')).token), activeAuth.token);
        assert.equal(await page.locator('.profile-login').count(), 0);
        assert.equal(await page.getByText('Old synthetic account coupon', { exact: true }).count(), 0);
        assert.equal(await page.locator('.profile-error').count(), 0);
        if (!scenario.includes('member-change')) assert(await page.getByText('New synthetic account coupon', { exact: true }).isVisible());
        else assert.equal(await page.getByRole('button', { name: '我的券', exact: false }).count(), 0);
        assert.equal(couponCalls, scenario.includes('member-change') ? 1 : 2);
        assert.deepEqual(errors, []);
        results.push({ scenario, couponCalls, oldResponseDiscarded: true, currentLoginPreserved: true });
        await context.close();
      }
      fs.writeFileSync(path.join(out, 'late-result.json'), JSON.stringify({ mode, synthetic: true, results }, null, 2));
      console.log(JSON.stringify(results));
      return;
    }
    for (const width of [375, 390]) {
      const member = width === 375;
      const auth = { ...fixture.accounts.full, user: { ...fixture.accounts.full.user, is_member: member, member_type: member ? 'annual' : null, member_expire_at: member ? '2027-10-07T00:00:00Z' : null } };
      const context = await browser.newContext({ viewport: { width, height: 844 } });
      const calls = [];
      await context.route('**/api/v1/auth/h5/me', async route => {
        calls.push('identity');
        await route.fulfill({ json: auth.user });
      });
      for (const [suffix, value] of [['orders', []], ['selection-sessions/mine', { items: [] }], ['coupons', { items: [] }]]) {
        await context.route(`**/api/v1/${suffix}`, async route => {
          calls.push(suffix);
          await new Promise(resolve => setTimeout(resolve, 250));
          await route.fulfill({ json: value });
        });
      }
      await context.addInitScript(value => localStorage.setItem('hxy_diy_customer_auth', JSON.stringify(value)), auth);
      const page = await context.newPage();
      const errors = [], requests = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', request => requests.push({ url: request.url(), method: request.method() }));
      await page.goto(fixture.url);
      await page.locator('.project-card').first().waitFor();
      const menuText = await page.locator('.project-card').first().innerText();
      await page.locator('.miniapp-profile-entry').click();
      await page.locator('.profile-card').waitFor();
      await page.locator('.toast').waitFor({ state: 'hidden' });
      await page.waitForFunction(() => !document.querySelector('.profile-empty')?.textContent.includes('正在加载'));
      await page.evaluate(() => {
        window.profileProbe = { loadingEntries: 0, cardRemoved: 0 };
        window.profileCard = document.querySelector('.profile-card');
        window.profileObserver = new MutationObserver(records => {
          for (const record of records) for (const node of record.addedNodes) {
            if (node.nodeType === 1 && node.matches('.profile-empty') && node.textContent.includes('正在加载')) window.profileProbe.loadingEntries++;
          }
          if (!window.profileCard.isConnected) window.profileProbe.cardRemoved++;
        });
        window.profileObserver.observe(document.querySelector('.profile-page'), { childList: true, subtree: true });
      });
      const callsAtStart = calls.length;
      // Two actual five-second identity cycles; no timer acceleration.
      await page.waitForTimeout(11_000);
      await page.evaluate(() => { window.dispatchEvent(new Event('focus')); document.dispatchEvent(new Event('visibilitychange')); });
      await page.waitForTimeout(700);
      const probe = await page.evaluate(() => window.profileProbe);
      const counts = Object.fromEntries(['identity', 'orders', 'selection-sessions/mine', 'coupons'].map(key => [key, calls.filter(value => value === key).length]));
      assert(counts.identity >= 3, 'Original identity refresh cycles must actually run');
      assert.equal(probe.cardRemoved, 0, 'The personal card must not remount');
      if (mode === 'before') {
        assert(counts.orders >= 3 && counts['selection-sessions/mine'] >= 3);
        assert(probe.loadingEntries >= 2);
      } else {
        assert.equal(counts.orders, 0);
        assert.equal(counts['selection-sessions/mine'], 0);
        assert.equal(counts.coupons, member ? 0 : 1);
        assert.equal(probe.loadingEntries, 0);
        for (const text of ['出示动态会员码', '到店记录', '累计会员省', '完成首次服务后可查看']) assert.equal(await page.getByText(text, { exact: true }).count(), 0);
        assert(!requests.some(item => /member-code|trusted-device/.test(item.url)));
        if (member) {
          assert(await page.getByText('年度权益卡会员', { exact: false }).isVisible());
          assert(await page.getByText('有效期至', { exact: false }).isVisible());
        } else assert(await page.getByRole('button', { name: '我的券', exact: false }).isVisible());
      }
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.screenshot({ path: path.join(out, `${mode}-${width}-my.png`) });
      await page.locator('.profile-pending-task').filter({ hasText: '我的检测报告' }).click();
      await page.locator('.my-reports').waitFor();
      await page.getByRole('button', { name: '返回我的', exact: true }).click();
      await page.locator('.profile-card').waitFor();
      await page.getByRole('button', { name: '返回', exact: true }).click();
      await page.locator('.miniapp-profile-entry').waitFor();
      assert.equal(await page.locator('.project-card').first().innerText(), menuText);
      assert(await page.getByText('评价与建议', { exact: true }).isVisible());
      await page.locator('.miniapp-profile-entry').click();
      await page.getByRole('button', { name: '退出登录', exact: true }).click();
      await page.locator('.profile-login').waitFor();
      assert.equal(await page.evaluate(() => localStorage.getItem('hxy_diy_customer_auth')), null);
      assert.deepEqual(errors, []);
      results.push({ width, member, counts, loadingEntries: probe.loadingEntries, cardRemounted: false, callsDuringObservation: calls.length - callsAtStart, reportReturnLogout: true, menuPriceUnchanged: true, menuFeedbackPreserved: true });
      await context.close();
    }
    fs.writeFileSync(path.join(out, `${mode}-result.json`), JSON.stringify({ mode, synthetic: true, identityPeriodMs: 5000, observationMs: 11000, results }, null, 2));
    console.log(JSON.stringify(results));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

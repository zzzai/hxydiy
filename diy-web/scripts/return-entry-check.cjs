// Customer return navigation over isolated API; only explicit fixture actions write local state.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const fixture = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
assert.equal(fixture.synthetic, true);
assert.equal(new URL(fixture.apiBase).hostname, '127.0.0.1');
const out = path.resolve('output/playwright/customer-return-cta-wecom-02');
fs.mkdirSync(out, { recursive: true });
const contactUrl = 'https://work.weixin.qq.com/u/vcd649012bd26ad232?v=5.0.10.79677&bb=fcec4c6148';
const stable = 'http://127.0.0.1:4185/?store=1&view=return';
(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  const checks = [];
  try {
    for (const width of [375, 390]) {
      const context = await browser.newContext({ viewport: { width, height: 844 } });
      await context.addInitScript(auth => {
        localStorage.setItem('hxy_diy_customer_auth', JSON.stringify(auth));
        window.copiedEntry = '';
        Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async value => { if (window.failCopy) throw new Error('Synthetic clipboard denial'); window.copiedEntry = value; } } });
      }, fixture.accounts.full);
      const page = await context.newPage();
      await page.goto(fixture.url);
      await page.locator('.return-entry-banner').waitFor();
      await page.locator('.toast').waitFor({ state: 'hidden' });
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.screenshot({ path: path.join(out, `${width}-home.png`) });
      await page.locator('.return-entry-banner').getByRole('button', { name: '查看入口', exact: true }).click();
      await page.getByRole('heading', { name: '下次来，不用找沙发码', exact: true }).waitFor();
      await page.getByRole('heading', { name: '荷小悦草本轻养', exact: true }).waitFor();
      await page.getByRole('button', { name: '复制名称', exact: true }).click();
      await page.getByText('名称已复制，可到微信搜索。', { exact: true }).waitFor();
      assert.equal(await page.evaluate(() => window.copiedEntry), '荷小悦草本轻养');
      await page.evaluate(() => { window.failCopy = true; });
      await page.getByRole('button', { name: '复制名称', exact: true }).click();
      await page.getByText('无法自动复制，可在微信搜索「荷小悦草本轻养」。', { exact: true }).waitFor();
      assert.equal(await page.getByRole('textbox', { name: '门店固定入口' }).count(), 0);
      await page.screenshot({ path: path.join(out, `${width}-copy-fallback.png`) });
      await page.getByRole('button', { name: '关闭入口提示' }).click();
      await page.getByRole('button', { name: '关闭服务号入口提示' }).click();
      assert.equal(await page.locator('.return-entry-banner').count(), 0);
      assert.equal(await page.evaluate(() => localStorage.getItem('hxy_diy_return_notice_closed_1')), '1');
      await page.reload();
      await page.locator('.miniapp-profile-entry').click();
      await page.locator('.profile-return-tools').waitFor();
      assert.equal(await page.locator('.return-entry-banner').count(), 0);
      await page.locator('.toast').waitFor({ state: 'hidden' });
      await page.screenshot({ path: path.join(out, `${width}-my.png`) });
      await page.locator('.return-contact-card button').click();
      const image = page.locator('.store-contact-qr');
      await image.waitFor();
      const png = (await image.getAttribute('src')).split(',')[1];
      const qrPath = path.join(out, `${width}-contact-qr.png`);
      fs.writeFileSync(qrPath, Buffer.from(png, 'base64'));
      const decoded = execFileSync('python', ['-c', 'import cv2,sys; print(cv2.QRCodeDetector().detectAndDecode(cv2.imread(sys.argv[1]))[0])', qrPath], { encoding: 'utf8' }).trim();
      assert.equal(decoded, contactUrl);
      await page.getByText('长按二维码，添加店长企微', { exact: true }).waitFor();
      assert.equal(await page.getByRole('link', { name: '添加门店企微' }).count(), 0);
      assert.equal(await image.evaluate(img => getComputedStyle(img).userSelect), 'auto');
      assert.equal(await image.evaluate(img => img.oncontextmenu), null);
      await page.screenshot({ path: path.join(out, `${width}-contact.png`) });
      await page.getByRole('button', { name: '关闭入口提示' }).click();
      await page.locator('.profile-tuesday-card summary').click();
      assert.match(await page.locator('.profile-tuesday-card').innerText(), /补差和叠加规则.*门店人工确认/s);
      await page.screenshot({ path: path.join(out, `${width}-tuesday.png`) });
      await context.close();
      for (const state of ['no-seat', 'released', 'occupied', 'unconfigured-store']) {
        const returned = await browser.newContext({ viewport: { width, height: 844 } });
        await returned.addInitScript(({ auth, state }) => {
          if (!sessionStorage.getItem('synthetic-return-auth-seeded')) {
            localStorage.setItem('hxy_diy_customer_auth', JSON.stringify(auth));
            sessionStorage.setItem('synthetic-return-auth-seeded', '1');
          }
          localStorage.setItem('hxy_diy_entry_1_sofa-01', JSON.stringify({ accessToken: 'STALE', session: { id: 'OLD', status: 'submitted' }, occupancy: { status: state }, positionCode: 'sofa-01' }));
        }, { auth: fixture.accounts.full, state });
        const returnPage = await returned.newPage();
        const apiRequests = [];
        returnPage.on('request', req => { if (req.url().includes('/api/v1/')) apiRequests.push({ method: req.method(), url: req.url() }); });
        const entry = state === 'no-seat' ? 'http://127.0.0.1:4185/?store=1' : state === 'unconfigured-store' ? 'http://127.0.0.1:4185/?store=2&view=return' : stable + '&seat=sofa-01&source=store_qr&session=OLD&token=OLD&auth=OLD&qr=OLD&report=OLD';
        await returnPage.goto(entry);
        await returnPage.locator('.profile-return-tools').waitFor();
        assert(!apiRequests.some(req => req.method !== 'GET'));
        assert(!apiRequests.some(req => /entry-sessions|occupancies|selection-sessions|service-positions/.test(req.url)));
        assert(!new URL(returnPage.url()).searchParams.has('seat'));
        assert(await returnPage.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        if (state === 'unconfigured-store') {
          await returnPage.locator('.return-contact-card button').click();
          await returnPage.getByText('门店线上联系方式尚未配置，到店可联系前台。', { exact: true }).waitFor();
          assert.equal(await returnPage.locator('.store-contact-qr').count(), 0);
          assert.equal(await returnPage.getByRole('link', { name: '添加门店企微' }).count(), 0);
        }
        if (state === 'no-seat') {
          await returnPage.getByRole('button', { name: '我的检测报告', exact: false }).click();
          await returnPage.waitForFunction(() => document.querySelector('.my-reports-consent') || document.querySelector('.my-reports-list'));
          if (await returnPage.getByRole('checkbox').count()) {
            await returnPage.getByRole('checkbox').check();
            await returnPage.getByRole('button', { name: '同意并查看' }).click();
          }
          await returnPage.locator('.my-reports-row').first().waitFor();
          assert(!apiRequests.some(req => /send-code|auth\/h5\/login$/.test(req.url)));
          await returnPage.getByRole('button', { name: '返回我的', exact: true }).click();
          await returnPage.getByRole('button', { name: '退出登录' }).click();
          await returnPage.getByPlaceholder('请输入手机号').waitFor();
          assert.equal(await returnPage.evaluate(() => localStorage.getItem('hxy_diy_customer_auth')), null);
          await returnPage.reload();
          await returnPage.getByPlaceholder('请输入手机号').waitFor();
          assert.equal(await returnPage.evaluate(() => localStorage.getItem('hxy_diy_customer_auth')), null);
          await returned.route('**/api/v1/auth/h5/send-code', route => route.fulfill({ json: { sent: true, expires_in_seconds: 60 } }));
          await returned.route('**/api/v1/auth/h5/login', route => route.fulfill({ json: fixture.accounts.full }));
          await returnPage.getByPlaceholder('请输入手机号').fill(fixture.accounts.full.user.phone);
          await returnPage.getByRole('button', { name: '获取验证码' }).click();
          await returnPage.getByPlaceholder('6 位验证码').fill('123456');
          await returnPage.getByRole('button', { name: '登录查看记录' }).click();
          await returnPage.getByRole('button', { name: '退出登录' }).waitFor();
          assert(!apiRequests.some(req => /entry-sessions|occupancies|selection-sessions/.test(req.url)));
        }
        if (state === 'no-seat') {
          await returnPage.locator('.profile-page > header > button').first().click();
          const main = returnPage.getByRole('link', { name: '到店选项目', exact: true });
          assert.equal(await main.getAttribute('class'), 'return-primary');
          assert.equal(await returnPage.getByRole('button', { name: '打开我的' }).getAttribute('class'), 'return-menu-link');
          await returnPage.screenshot({ path: path.join(out, `${width}-welcome.png`) });
          await returnPage.getByRole('button', { name: '打开我的' }).click();
          await returnPage.locator('.profile-return-tools').waitFor();
          await returnPage.locator('.profile-page > header > button').first().click();
          const requestCount = apiRequests.length;
          await main.click();
          await returnPage.getByRole('heading', { name: '选择您所在的沙发', exact: true }).waitFor();
          assert.equal(new URL(returnPage.url()).searchParams.get('view'), 'menu');
          assert(!apiRequests.slice(requestCount).some(req => req.method !== 'GET' && /entry-sessions|occupancies|selection-sessions/.test(req.url)));
          await returnPage.screenshot({ path: path.join(out, `${width}-position-confirmation.png`) });
        }
        checks.push({ width, state, noAutomaticWrites: true, noSeatContextRead: true, noOverflow: true });
        await returned.close();
      }
    }
    fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify({ productionWrites: false, environment: 'localhost synthetic identity/consent; stale occupancy records; OTP responses and contact destination are synthetic; QR payload is user-confirmed real contact', realContactConfiguredStores: [1], checks }, null, 2));
    console.log(JSON.stringify({ passed: checks.length, report: path.join(out, 'result.json') }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

// Frozen backend menu data; browser rendering only, no production requests or orders.
const { chromium } = require('playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const path = require('node:path');
const fixture = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
assert.equal(fixture.synthetic, true);
assert.equal(new URL(fixture.apiBase).hostname, '127.0.0.1');
const source = execFileSync('git', ['show', 'origin/menu-contract-218:hxy-server/scripts/reconcile_menu_20261007.py'], { encoding: 'utf8' });
const entries = [...source.matchAll(/\("(hxy-[^"]+)", "([^"]+)", (None|\d+), (None|\d+), (\d+),\s*"([^"]+)"\)/g)].map((m) => ({ code: m[1], name: m[2], duration_min: m[3] === 'None' ? null : Number(m[3]), store: m[4] === 'None' ? null : Number(m[4]), member: Number(m[5]), summary: m[6] }));
assert.equal(entries.length, 14);
const out = path.resolve('output/playwright/menu-catalog-20261009');
fs.mkdirSync(out, { recursive: true });
(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  const checks = [];
  try {
    for (const width of [375, 390]) {
      const context = await browser.newContext({ viewport: { width, height: 844 } });
      await context.route('**/api/v1/projects?*', async (route) => {
        const response = await route.fetch();
        const data = await response.json();
        if (!data.items.some((item) => item.code === 'hxy-nvshen-60')) {
          const base = data.items.find((item) => item.code === 'hxy-qiqing-30');
          data.items.push({ ...base, id: 900014, code: 'hxy-nvshen-60', option_groups: [], catalog_version_id: null });
        }
        for (const item of data.items) {
          const entry = entries.find((value) => value.code === item.code);
          if (!entry) continue;
          Object.assign(item, { name: entry.name, summary: entry.summary, duration_min: entry.duration_min, price_label: entry.code === 'hxy-taoke-60' ? '10次/套' : entry.duration_min ? '分钟' : '次' });
          item.prices = item.prices.filter((price) => !['store', 'member'].includes(price.price_type));
          if (entry.store !== null) item.prices.push({ price_type: 'store', amount_cents: entry.store });
          item.prices.push({ price_type: 'member', amount_cents: entry.member });
        }
        await route.fulfill({ response, json: data });
      });
      const page = await context.newPage();
      await page.goto(fixture.url);
      await page.locator('.mini-project-row').first().waitFor();
      for (const entry of entries) {
        const card = page.locator('.mini-project-row').filter({ has: page.getByRole('heading', { name: entry.name, exact: true }) });
        await card.scrollIntoViewIfNeeded();
        assert.equal(await card.count(), 1, entry.code);
        if (entry.store === null) {
          assert.match(await card.innerText(), /会员.*980.*套/s);
          assert.doesNotMatch(await card.locator('.project-meta').innerText(), /门店/);
        }
        await card.click();
        const detail = page.getByRole('dialog').last();
        await detail.waitFor();
        await page.waitForFunction(() => {
          const dialog = [...document.querySelectorAll('[role="dialog"]')].at(-1);
          return dialog && Number(getComputedStyle(dialog).opacity) >= 0.99;
        });
        const rendered = await detail.locator('.detail-intro-copy').innerText();
        assert.equal(rendered.replace(/\s|·/g, ''), entry.summary.replace(/\s|[+＋]/g, ''), entry.code);
        if (entry.duration_min === null) assert.doesNotMatch((await detail.locator('.detail-intro-facts').allTextContents()).join(' '), /\d+分钟/);
        if (entry.store === null) {
          assert.doesNotMatch(await detail.locator('.mini-detail-price').innerText(), /门店价/);
          assert.match(await detail.locator('.mini-detail-price').innerText(), /10次\/套/);
        }
        await page.screenshot({ path: path.join(out, `${width}-${entry.code}.png`) });
        checks.push({ width, code: entry.code, fullSummary: true, inferredDuration: false });
        await detail.getByRole('button', { name: '返回项目列表', exact: true }).click();
      }
      await context.close();
    }
    fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify({ environment: 'localhost; frozen PR218 catalog response over isolated synthetic API', productionWrites: false, submissionTested: false, checks }, null, 2));
    console.log(JSON.stringify({ passed: checks.length, report: path.join(out, 'result.json') }));
  } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });

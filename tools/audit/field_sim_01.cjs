// Real HTTP/browser integration against an explicitly isolated local server.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '../..');
const output = path.join(root, 'output/playwright/field-sim-01');
if (!process.env.FIELD_SIM_MANIFEST) throw new Error('FIELD_SIM_MANIFEST must point to an external synthetic seed manifest');
const seed = JSON.parse(fs.readFileSync(process.env.FIELD_SIM_MANIFEST, 'utf8'));
const base = process.env.FIELD_SIM_BASE || 'http://127.0.0.1:4180';
if (!seed.synthetic || new URL(base).hostname !== '127.0.0.1' || seed.positions.some(position => new URL(position.url).origin !== base)) throw new Error('Only an explicitly synthetic localhost environment is allowed');
const results = [];
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
fs.mkdirSync(output, { recursive: true });
async function check(name, task) {
  try { results.push({ name, status: 'pass', evidence: await task() }); }
  catch (error) { results.push({ name, status: 'fail', error: error.message }); }
  fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify({ revision: '1168b336d3a042736eef3b75587cfe65f2b2b29d', environment: 'synthetic SQLite / real localhost API and H5', results }, null, 2));
}
async function api(context, method, url, data, headers = {}) {
  const response = await context.request.fetch(base + '/api/v1' + url, { method, data, headers });
  const body = await response.json();
  return { status: response.status(), body };
}
async function main() {
  const browser = await chromium.launch({ ...(process.env.FIELD_SIM_BROWSER ? { executablePath: process.env.FIELD_SIM_BROWSER } : { channel: 'chrome' }), headless: true });
  const contexts = [];
  const pages = [];
  const entries = [];
  for (const width of [375, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 844 }, userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile MicroMessenger/8.0.50', isMobile: true, hasTouch: true });
    contexts.push(context);
    await context.tracing.start({ screenshots: true, snapshots: true });
    const page = await context.newPage();
    pages.push(page);
    page.on('response', async response => {
      if (response.url().includes('/entry-sessions') && response.status() === 200) entries[contexts.indexOf(context)] = await response.json();
    });
    await page.goto(seed.positions[0].url);
    await page.getByRole('button', { name: /^(选择|调整)现煮草本泡$/ }).waitFor();
    await check(`menu_${width}`, async () => {
      assert.equal(await page.locator('.miniapp-promo').filter({ hasText: '90分钟精油SPA' }).innerText(), '门店推荐\n90分钟精油SPA\n¥179');
      const metrics = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }));
      assert.ok(metrics.document <= metrics.viewport);
      await page.screenshot({ path: path.join(output, `menu-${width}.png`) });
      return metrics;
    });
    await page.getByRole('button', { name: /^(选择|调整)现煮草本泡$/ }).click();
    await page.locator('.herbal-formula-options').waitFor();
    await check(`five_formulas_${width}`, async () => {
      const names = ['玉竹百合汤', '玫瑰郁金汤', '杜仲菟丝汤', '丹参当归汤', '茯苓薏仁汤'];
      const buttons = page.locator('.herbal-formula-options button');
      assert.equal(await buttons.count(), 5);
      const seen = [];
      for (let i = 0; i < 5; i++) {
        await buttons.nth(i).click();
        const title = await page.locator('.herbal-formula-heading').innerText();
        assert.ok(names.includes(title));
        const herbs = await page.locator('.herbal-formula-herbs').innerText();
        const count = Number((await page.locator('.herbal-formula-count').innerText()).match(/\d+/)[0]);
        assert.equal(herbs.split('、').length, count);
        const metrics = await page.locator('.herbal-formula-herbs').evaluate(el => ({ scroll: el.scrollHeight, height: el.clientHeight }));
        assert.ok(metrics.scroll <= metrics.height + 1);
        seen.push({ title, count });
      }
      await buttons.nth(1).click();
      await page.getByRole('button', { name: /适中/ }).click();
      await page.locator('.toast').waitFor({ state: 'hidden' });
      await page.locator('.herbal-formula-group').screenshot({ path: path.join(output, `formula-${width}.png`) });
      const hero = await page.locator('.mini-detail-hero').evaluate(el => ({ height: el.clientHeight, fit: getComputedStyle(el).objectFit, loaded: el.complete && el.naturalWidth > 0 }));
      assert.ok(hero.height <= 290 && hero.loaded && hero.fit === 'contain');
      return { seen, hero };
    });
    await page.locator('.mini-detail-actions button.primary').click();
    await page.locator('.selection-summary').waitFor();
    await check(`cart_preferences_${width}`, async () => {
      await page.locator('.selection-summary').click();
      const text = await page.locator('.selection-summary-sheet').innerText();
      assert.ok(text.includes('玫瑰郁金汤') && text.includes('适中'));
      const size = await page.locator('.selection-sheet-total > p').evaluate(el => getComputedStyle(el).fontSize);
      assert.equal(size, '13px');
      await page.locator('.selection-summary-sheet').screenshot({ path: path.join(output, `cart-${width}.png`) });
      await page.getByRole('button', { name: '关闭本次已选' }).click();
      return { preferencesVisible: true, noteFontSize: size };
    });
  }
  const [first, second] = entries;
  const sid = first.session.id;
  const header = token => ({ 'X-Collaboration-Token': token });
  await check('independent_context_shared_draft', async () => {
    assert.equal(first.session.id, second.session.id);
    assert.notEqual(first.collaboration_token, second.collaboration_token);
    const read = await api(contexts[1], 'GET', `/selection-sessions/${sid}`, undefined, header(second.collaboration_token));
    assert.equal(read.status, 200);
    assert.equal(read.body.items.length, 1);
    return { sameSession: true, distinctTokens: true, itemCount: read.body.items.length };
  });
  await check('delayed_poll_offline_resume', async () => {
    let active = 0, maximum = 0, reads = 0;
    const pattern = `**/selection-sessions/${sid}`;
    await pages[1].route(pattern, async route => {
      if (route.request().method() !== 'GET') return route.continue();
      reads++; active++; maximum = Math.max(maximum, active);
      try { const response = await route.fetch(); await sleep(4200); await route.fulfill({ response }); }
      catch {} finally { active--; }
    });
    await sleep(9500);
    assert.equal(maximum, 1);
    await contexts[1].setOffline(true);
    await sleep(1000);
    const offlineStart = reads;
    await sleep(4500);
    assert.equal(reads, offlineStart);
    await contexts[1].setOffline(false);
    await sleep(5000);
    assert.ok(reads > offlineStart);
    await pages[1].unroute(pattern);
    return { delayedMs: 4200, maxConcurrentReads: maximum, offlineReadCount: reads - offlineStart };
  });
  await check('version_conflict_no_overwrite', async () => {
    const before = await api(contexts[0], 'GET', `/selection-sessions/${sid}`, undefined, header(first.collaboration_token));
    const payload = { items: before.body.items, diy_preferences: before.body.diy_preferences, expected_version: before.body.cart_version };
    const updated = { ...payload, items: payload.items.map(item => ({ ...item, quantity: 2 })) };
    const saved = await api(contexts[0], 'PATCH', `/selection-sessions/${sid}`, updated, header(first.collaboration_token));
    assert.equal(saved.status, 200);
    const stale = await api(contexts[1], 'PATCH', `/selection-sessions/${sid}`, { ...payload, items: [] }, header(second.collaboration_token));
    assert.equal(stale.status, 409);
    const read = await api(contexts[1], 'GET', `/selection-sessions/${sid}`, undefined, header(second.collaboration_token));
    assert.equal(read.body.items.length, 1);
    assert.equal(read.body.items[0].quantity, 2);
    return { staleHttp: stale.status, preservedItemCount: 1, preservedQuantity: 2 };
  });
  await check('cross_position_draft_isolation', async () => {
    const p = seed.positions[1];
    const entered = await api(contexts[1], 'POST', '/entry-sessions', { store_id: seed.store_id, position_code: p.position_code, source: p.source, entry_token: p.token });
    assert.equal(entered.status, 200);
    assert.notEqual(entered.body.session.id, sid);
    assert.equal(entered.body.session.items.length, 0);
    return { independentSession: true, itemCount: 0 };
  });
  await check('submit_idempotent_lock', async () => {
    const read = await api(contexts[0], 'GET', `/selection-sessions/${sid}`, undefined, header(first.collaboration_token));
    const payload = { items: read.body.items, diy_preferences: read.body.diy_preferences, expected_version: read.body.cart_version };
    const headers = { ...header(first.collaboration_token), 'Idempotency-Key': 'field-sim-submit-001' };
    const submitted = await api(contexts[0], 'POST', `/selection-sessions/${sid}/revisions`, payload, headers);
    assert.equal(submitted.status, 200, JSON.stringify(submitted.body));
    const replay = await api(contexts[0], 'POST', `/selection-sessions/${sid}/revisions`, payload, headers);
    assert.deepEqual(replay, submitted);
    const blocked = await api(contexts[1], 'PATCH', `/selection-sessions/${sid}`, { ...payload, items: [] }, header(second.collaboration_token));
    assert.equal(blocked.status, 403);
    return { submitHttp: 200, identicalReplay: true, editAfterSubmitHttp: blocked.status };
  });
  await check('front_technician_release_api', async () => {
    const front = { Authorization: 'Bearer ' + seed.admin_token };
    const tech = { Authorization: 'Bearer ' + seed.technician_token };
    const confirm = await api(contexts[0], 'POST', `/admin/v2/selection-sessions/${sid}/confirm`, {}, front);
    assert.equal(confirm.status, 200, JSON.stringify(confirm.body));
    const occupancy = first.occupancy.id;
    const begin = await api(contexts[0], 'POST', `/technician/occupancies/${occupancy}/confirm`, { idempotency_key: 'field-sim-tech-start' }, tech);
    assert.equal(begin.status, 200, JSON.stringify(begin.body));
    const end = await api(contexts[0], 'POST', `/technician/occupancies/${occupancy}/finish`, { idempotency_key: 'field-sim-tech-finish' }, tech);
    assert.equal(end.status, 200, JSON.stringify(end.body));
    const tasks = await api(contexts[0], 'GET', '/technician/tasks', undefined, tech);
    const task = tasks.body.items.find(item => item.selection_session_id === sid);
    const recordPayload = { user_id: task.user_id, selection_session_id: sid, schema_version: 7, taxonomy_version: 'service_handoff_v1', customer_confirmed: true, profile: { schema_version: 7, taxonomy_version: 'service_handoff_v1', communication: 'quiet', body_focus: [{ region: 'neck_shoulder', next_action: 'lighter' }], session_changes: ['temperature_lower'] }, signals: [], note: '' };
    const record = await api(contexts[0], 'POST', '/admin/v2/customer-profile-records', recordPayload, { ...tech, 'Idempotency-Key': 'field-sim-record-001' });
    assert.equal(record.status, 200, JSON.stringify(record.body));
    const release = await api(contexts[0], 'POST', `/admin/occupancies/${occupancy}/confirm-departure`, { reason: 'Synthetic acceptance complete' }, front);
    assert.equal(release.status, 200, JSON.stringify(release.body));
    const clean = await api(contexts[0], 'POST', `/admin/occupancies/${occupancy}/finish-cleaning`, { reason: 'Synthetic cleanup' }, front);
    assert.equal(clean.status, 200, JSON.stringify(clean.body));
    const p = seed.positions[0];
    const fresh = await api(contexts[0], 'POST', '/entry-sessions', { store_id: seed.store_id, position_code: p.position_code, source: p.source, entry_token: p.token, start_new_after_service: true });
    assert.equal(fresh.status, 200);
    assert.notEqual(fresh.body.session.id, sid);
    return { frontConfirm: confirm.status, technicianStart: begin.status, technicianFinish: end.status, record: record.status, released: true, freshDraft: fresh.body.session.status };
  });
  for (let i = 0; i < contexts.length; i++) await contexts[i].tracing.stop({ path: path.join(output, `trace-${i}.zip`) });
  await browser.close();
  console.log(JSON.stringify({ pass: results.filter(r => r.status === 'pass').length, fail: results.filter(r => r.status === 'fail').length, report: path.join(output, 'report.json') }));
}
main().catch(error => { fs.writeFileSync(path.join(output, 'fatal.json'), JSON.stringify({ error: error.stack })); console.error(error.message); process.exit(1); });

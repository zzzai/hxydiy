import assert from 'node:assert/strict';

// Run against the guest menu with an isolated store roster and no customer order writes.
export async function verifyTechnicianProfileReturn(page, card, { browserBack = false, storeVisit } = {}) {
  const list = page.getByRole('dialog', { name: '本店技师', exact: true });
  const scroller = page.locator('.technician-showcase > .technician-directory');
  await card.scrollIntoViewIfNeeded();
  const top = await scroller.evaluate(element => element.scrollTop);
  const label = (await card.locator('.technician-card-name').innerText()).replace(/\s+/g, ' ').trim();
  const filter = await scroller.locator('[aria-pressed="true"]').allTextContents();
  await card.click();
  const profile = page.locator('dialog.technician-sheet[open]');
  await profile.getByRole('heading', { name: label, exact: true }).waitFor();
  const box = await profile.boundingBox();
  const viewport = page.viewportSize();
  assert.ok(box && viewport && box.y > 4 && box.height < viewport.height - 4);
  if (viewport.width < 768) assert.ok(Math.abs(box.y + box.height - viewport.height) <= 2, 'Mobile sheet sits at the bottom');
  else assert.ok(Math.abs(box.y - (viewport.height - box.height) / 2) <= 2, 'Wide dialog is centered');
  assert.ok(await profile.evaluate(el => el.matches(':modal')));
  assert.ok(await scroller.isVisible(), 'The directory remains behind the modal');
  const picture = profile.locator('.technician-sheet-photo').first();
  if (await picture.count()) {
    await picture.click();
    const viewer = profile.locator('.technician-viewer');
    await viewer.waitFor();
    if (await viewer.getByRole('button', { name: '下一张' }).count()) {
      const first = await viewer.locator('img').getAttribute('src');
      await viewer.getByRole('button', { name: '下一张' }).click();
      assert.notEqual(await viewer.locator('img').getAttribute('src'), first);
    }
    await page.keyboard.press('Escape');
    await profile.getByRole('heading', { name: label, exact: true }).waitFor();
    assert.ok(await picture.evaluate(el => el === document.activeElement), 'Returning from the gallery restores photo focus');
  }
  assert.equal(await profile.getByRole('button', { name: '看本店项目', exact: true }).count(), 0);
  assert.equal(await profile.getByRole('button', { name: /^看.+号技师$/ }).count(), 0);
  assert.equal(await profile.getByRole('button', { name: '本份服务点名', exact: true }).count(), 0);
  if (storeVisit) {
    const visit = profile.getByRole('region', { name: '到店信息' });
    const disclosure = visit.locator('details');
    assert.equal(await disclosure.evaluate(element => element.open), false, 'Visit logistics start collapsed');
    await disclosure.locator('summary').click();
    await visit.getByText(storeVisit.hours, { exact: true }).waitFor();
    await visit.getByText(storeVisit.address, { exact: true }).waitFor();
    const button = visit.getByRole('button', { name: '复制门店地址' });
    await page.evaluate(() => {
      Object.defineProperty(navigator, 'clipboard', { configurable: true, value: {
        writeText: async value => { document.documentElement.dataset.copiedAddress = value; }
      } });
    });
    await button.click();
    await visit.getByText('地址已复制', { exact: true }).waitFor();
    assert.equal(await page.evaluate(() => document.documentElement.dataset.copiedAddress), storeVisit.address);
    await page.evaluate(() => {
      Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined });
    });
    await button.click();
    await visit.getByText('请选中上方地址复制', { exact: true }).waitFor();
  }
  if (browserBack) await page.goBack();
  else await profile.getByRole('button', { name: '返回本店技师', exact: true }).click();
  await profile.waitFor({state: 'detached'});
  await list.waitFor();
  assert.deepEqual(await scroller.locator('[aria-pressed="true"]').allTextContents(), filter);
  await card.evaluate(element => new Promise(resolve => requestAnimationFrame(() => resolve())));
  assert.ok(await card.evaluate(element => document.activeElement === element), 'Focus returns to the same technician');
  assert.ok(Math.abs(await scroller.evaluate(element => element.scrollTop) - top) <= 2, 'Directory scroll is preserved');
}

export async function verifyNamedProjectDraft(page, { name, storeId, projectId, technicianId }) {
  const profile = page.locator('dialog.technician-sheet[open]');
  const service = profile.getByRole('listitem').filter({ has: page.getByText(name, { exact: true }) });
  const checked = page.waitForResponse(response =>
    response.request().method() === 'GET'
      && new URL(response.url()).pathname.endsWith('/stores/' + storeId + '/projects/' + projectId + '/selectable-technicians'));
  await service.getByRole('button', { name: /选项目并点名/ }).click();
  assert.equal((await checked).status(), 200);
  const picker = page.getByRole('combobox', { name: '本份服务技师', exact: true });
  await picker.waitFor();
  assert.equal(await picker.inputValue(), String(technicianId), 'The chosen project opens with the verified technician in this portion');
}

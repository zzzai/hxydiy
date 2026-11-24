import assert from 'node:assert/strict';

// Run against the guest menu with an isolated store roster and no customer order writes.
export async function verifyTechnicianProfileReturn(page, card, { browserBack = false, storeVisit } = {}) {
  const list = page.getByRole('dialog', { name: '本店技师', exact: true });
  const scroller = list.locator('.technician-directory');
  await card.scrollIntoViewIfNeeded();
  const top = await scroller.evaluate(element => element.scrollTop);
  const label = await card.locator('.technician-card-name').innerText();
  await card.click();
  const profile = page.getByRole('dialog', { name: '技师主页', exact: true });
  await profile.getByRole('heading', { name: label, exact: true }).waitFor();
  const box = await profile.boundingBox();
  const height = await page.evaluate(() => innerHeight);
  assert.ok(box && Math.abs(box.y) <= 1 && Math.abs(box.height - height) < 2, 'Profile covers the entire mobile viewport');
  assert.equal(await profile.getByRole('button', { name: '看本店项目', exact: true }).count(), 0);
  assert.equal(await profile.getByRole('button', { name: /^看.+号技师$/ }).count(), 0);
  assert.equal(await profile.getByRole('button', { name: '本份服务点名', exact: true }).count(), 0);
  if (storeVisit) {
    const visit = profile.getByRole('region', { name: '到店信息' });
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
  await list.waitFor();
  await card.evaluate(element => new Promise(resolve => requestAnimationFrame(() => resolve())));
  assert.ok(await card.evaluate(element => document.activeElement === element), 'Focus returns to the same technician');
  assert.ok(Math.abs(await scroller.evaluate(element => element.scrollTop) - top) <= 2, 'Directory scroll is preserved');
}

export async function verifyNamedProjectDraft(page, { name, storeId, projectId, technicianId }) {
  const profile = page.getByRole('dialog', { name: '技师主页', exact: true });
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

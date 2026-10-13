import assert from 'node:assert/strict';

// Replay through the documented CUA tab API against the local synthetic server.
export async function recoverSyntheticSession(tab, baseUrl, fixtureTag) {
  await tab.goto(`${baseUrl}/?store=1&view=reports&case=setup-${fixtureTag}`);
  const dialog = tab.playwright.getByRole('dialog');
  const source = tab.playwright.getByRole('heading', { name: '合成原站报告', exact: true });
  await dialog.or(source).waitFor({ state: 'visible', timeoutMs: 10000 });
  const state = await tab.playwright.domSnapshot();
  if (state.includes('dialog')) {
    await tab.playwright.getByPlaceholder('请输入手机号').fill('13800000001');
    await tab.playwright.getByPlaceholder('6 位验证码').fill('123456');
    await dialog.getByRole('button', { name: '登录并查看报告', exact: true }).click();
  }
  await source.waitFor({ state: 'visible', timeoutMs: 10000 });
}

export async function sessionProtectionCase(tab, baseUrl, scenario) {
  await recoverSyntheticSession(tab, baseUrl, scenario);
  await tab.goto(`${baseUrl}/?store=1&view=reports&case=${scenario}`);
  await tab.playwright.getByRole('heading', { name: '合成原站报告', exact: true }).waitFor({ state: 'visible', timeoutMs: 10000 });
  await tab.back();
  await tab.playwright.getByRole('button', { name: '历史报告', exact: true }).waitFor({ state: 'visible', timeoutMs: 10000 });
  await tab.playwright.domSnapshot();
  if (scenario.startsWith('after-history-')) {
    await tab.playwright.getByRole('button', { name: '历史报告', exact: true }).click();
    await tab.playwright.getByRole('button', { name: '检测报告 2026-10-13 10:00 查看报告', exact: true }).waitFor({ state: 'visible' });
    await tab.playwright.domSnapshot();
    if (scenario === 'after-history-inflight') {
      await tab.playwright.getByRole('button', { name: '返回', exact: true }).click();
      await tab.playwright.domSnapshot();
      await tab.playwright.getByRole('button', { name: '再次查看报告', exact: true }).click();
      await tab.playwright.domSnapshot();
    }
  } else {
    await tab.playwright.getByRole('button', { name: '撤回DIY报告查看授权', exact: true }).click();
    await tab.playwright.domSnapshot();
  }
  for (let attempt = 0; attempt < 3; attempt++) {
    try { await tab.playwright.getByRole('dialog').waitFor({ state: 'visible', timeoutMs: 10000 }); break; }
    catch (reason) {
      const latest = await tab.playwright.domSnapshot();
      if (latest.includes('dialog "查看我的检测报告"')) break;
      if (attempt === 2) throw reason;
    }
  }
  const state = await tab.playwright.domSnapshot();
  assert.ok(state.includes('dialog "查看我的检测报告"'), 'Identity failure must return to phone verification');
  assert.ok(!state.includes('2026-10-13') && !/138\*\*\*\*000[12]/.test(state), 'Old report rows and account identity must be cleared');
  assert.ok((await tab.url()).includes('view=reports'), 'In-flight old report must not navigate');
  return { case: scenario, passed: true, loginRequired: true, oldDataCleared: true, staysAtEntry: true };
}

import assert from 'node:assert/strict';
import test from 'node:test';
import { technicianMobileHome, technicianMobileTabs } from '../src/technician/technicianMobile.ts';
import { getEntryLoginPath, getPostLoginRedirect } from '../src/auth.ts';
import { readActiveToken, readActiveStaff, writeStaffSession, clearActiveStaffSession } from '../src/staffSession.ts';

function memory() {
  const values = new Map<string, string>();
  return { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value); }, removeItem: (key: string) => { values.delete(key); } };
}

test('manager mobile landing never returns the paused verifier or desktop', () => {
  assert.equal(technicianMobileHome('manager'), '/store');
  assert.deepEqual(technicianMobileTabs('manager'), []);
  assert.equal(getPostLoginRedirect('/technician/login', 'manager'), '/technician/store');
  assert.equal(getPostLoginRedirect('/admin/', 'manager'), '/admin/#/');
  assert.equal(technicianMobileHome('technician'), '/today');
});
test('manager workspace selects its own slot when another tab has a technician session', () => {
  const storage = memory();
  writeStaffSession(storage, { token: 'synthetic-manager', staff: { role: 'manager', technician_id: null, store_id: 1 } });
  writeStaffSession(storage, { token: 'synthetic-technician', staff: { role: 'technician', technician_id: 7, store_id: 1 } });
  assert.equal(readActiveToken(storage, '/technician/store'), 'synthetic-manager');
  assert.equal(readActiveStaff(storage, '/technician/store')?.role, 'manager');
  assert.equal(readActiveToken(storage, '/technician/today'), 'synthetic-technician');
});
test('manager logout and login do not fall back to a retained technician identity', () => {
  const storage = memory();
  writeStaffSession(storage, { token: 'synthetic-manager', staff: { role: 'manager' } });
  writeStaffSession(storage, { token: 'synthetic-technician', staff: { role: 'technician' } });
  clearActiveStaffSession(storage, '/technician/store');
  assert.equal(readActiveToken(storage, '/technician/store/login'), '');
  assert.equal(readActiveStaff(storage, '/technician/store/login'), null);
  assert.equal(readActiveToken(storage, '/technician/today'), 'synthetic-technician');
  assert.equal(getEntryLoginPath(true, '/technician/store'), '/technician/store/login');
});

test('manager OAuth completion reports the verified role while retaining the other session', async () => {
  const local = memory(), tab = memory();
  const location = { pathname: '/technician/store', assign: (_url: string) => {} };
  Object.assign(globalThis, { localStorage: local, sessionStorage: tab, window: { location, addEventListener: () => {} } });
  const { beginWecomEntry, completeWecomEntry, wecomLoginPath } = await import('../src/wecomSession.ts');
  writeStaffSession(local, { token: 'old-manager', staff: { role: 'manager', technician_id: null, store_id: 1 } });
  writeStaffSession(local, { token: 'retained-technician', staff: { role: 'technician', technician_id: 7, store_id: 1 } });
  const reply = (value: unknown) => new Response(JSON.stringify(value), { status: 200 });
  globalThis.fetch = async () => reply({ attempt_id: 'synthetic-attempt', authorization_url: 'https://open.weixin.qq.com/connect/oauth2/authorize' });
  await beginWecomEntry();
  assert.equal(readActiveToken(local, '/technician/today'), 'retained-technician');
  location.pathname = '/technician/wecom/complete';
  assert.equal(wecomLoginPath(), '/store/login');
  globalThis.fetch = async () => reply({
    token: 'verified-manager', auth_method: 'wecom', selector_token: null,
    staff: { id: 3, role: 'store_manager', technician_id: null, store_id: 1 },
    workspaces: [{ assignment_id: 3, role: 'store_manager', scope_type: 'store', scope_id: 1 }],
  });
  let verifiedRole = '';
  assert.equal(await completeWecomEntry(role => { verifiedRole = role; }), true);
  assert.equal(verifiedRole, 'manager');
  assert.equal(technicianMobileHome(verifiedRole), '/store');
  assert.equal(readActiveToken(local, '/technician/store'), 'verified-manager');
  assert.equal(readActiveToken(local, '/technician/today'), 'retained-technician');
});

test('leaving a pending manager callback never clears the retained WeCom technician', async () => {
  const local = memory(), tab = memory();
  Object.assign(globalThis, { localStorage: local, sessionStorage: tab, window: { location: { pathname: '/technician/wecom/complete' }, addEventListener: () => {} } });
  writeStaffSession(local, { token: 'retained-wecom-technician', staff: { role: 'technician', technician_id: 7, store_id: 1 }, authMethod: 'wecom' });
  tab.setItem('hxy_wecom_pending', JSON.stringify({ entry_nonce: 'pending-manager', attempt_id: 'attempt', entry_path: '/technician/store/wecom' }));
  const session = await import('../src/wecomSession.ts');
  let resolve!: (response: Response) => void;
  globalThis.fetch = () => new Promise<Response>(r => { resolve = r; });
  let accepted = false;
  const pending = session.completeWecomEntry(() => { accepted = true; });
  assert.equal(session.clearDepartingWecomSession(), true);
  assert.equal(readActiveToken(local, '/technician/today'), 'retained-wecom-technician');
  assert.equal(readActiveToken(local, '/technician/store'), '');
  resolve(new Response(JSON.stringify({ token: 'late-manager' }), { status: 200 }));
  assert.equal(await pending, false);
  assert.equal(accepted, false);
});

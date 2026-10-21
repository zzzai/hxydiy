import assert from 'node:assert/strict';
import test from 'node:test';
import { beginWecomEntry, clearStaffSession, commitStaffSession, completeWecomEntry, getSessionEpoch, hasManagerPendingDeepLink, isWecomEntryPending, isWecomSession, subscribeSessionEpoch, takeManagerPendingOrder, takeManagerPendingReview } from '../src/wecomSession.ts';

class MemoryStorage {
  values = new Map<string, string>();
  getItem(key: string) { return this.values.get(key) ?? null; }
  setItem(key: string, value: string) { this.values.set(key, value); }
  removeItem(key: string) { this.values.delete(key); }
}
const storage = new MemoryStorage();
const tabStorage = new MemoryStorage();
Object.assign(globalThis, { localStorage: storage, sessionStorage: tabStorage });
const navigations: string[] = [];
Object.assign(globalThis, { window: { location: { origin: 'https://synthetic.invalid', pathname: '/technician/today', assign: (url: string) => navigations.push(url) }, addEventListener: () => {} } });
const t1 = { token: 'synthetic-t1', staff: { id: 1, name: 'T1', role: 'technician', store_id: 1, technician_id: 1 }, auth_method: 'wecom' as const };
const t2 = { token: 'synthetic-t2', staff: { id: 2, name: 'T2', role: 'technician', store_id: 1, technician_id: 2 }, auth_method: 'wecom' as const };
const reply = (data: object) => new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } });
function reset() { clearStaffSession(); navigations.length = 0; }

test('entry synchronously drops old identity and notifies before OAuth network settles', async () => {
  reset(); commitStaffSession(t1, getSessionEpoch());
  let called = 0;
  const unsubscribe = subscribeSessionEpoch(() => called++);
  let resolve!: (r: Response) => void;
  globalThis.fetch = () => new Promise<Response>((r) => { resolve = r; });
  const start = beginWecomEntry();
  assert.equal(storage.getItem('hxy_admin_token'), null);
  assert.equal(isWecomEntryPending(), true);
  assert.ok(called > 0);
  resolve(reply({ attempt_id: 'a1', authorization_url: 'https://open.weixin.qq.com/connect/oauth2/authorize?state=synthetic', expires_in: 300 }));
  await start;
  assert.equal(navigations.length, 1);
  unsubscribe();
});
test('late authorize cannot replace a newer entry', async () => {
  reset();
  const pending: ((r: Response) => void)[] = [];
  globalThis.fetch = () => new Promise<Response>((r) => pending.push(r));
  const first = beginWecomEntry(); const second = beginWecomEntry();
  pending[1](reply({ attempt_id: 'a2', authorization_url: 'https://open.weixin.qq.com/connect/oauth2/authorize?state=new', expires_in: 300 }));
  await second;
  pending[0](reply({ attempt_id: 'a1', authorization_url: 'https://open.weixin.qq.com/connect/oauth2/authorize?state=old', expires_in: 300 }));
  await first;
  assert.deepEqual(navigations, ['https://open.weixin.qq.com/connect/oauth2/authorize?state=new']);
});
test('late exchange cannot overwrite a newer password session', async () => {
  reset();
  globalThis.fetch = async () => reply({ attempt_id: 'a1', authorization_url: 'https://open.weixin.qq.com/connect/oauth2/authorize', expires_in: 300 });
  await beginWecomEntry();
  let resolve!: (r: Response) => void;
  globalThis.fetch = () => new Promise<Response>((r) => { resolve = r; });
  const complete = completeWecomEntry();
  assert.equal(commitStaffSession({ ...t2, auth_method: undefined }, getSessionEpoch()), true);
  resolve(reply(t1));
  assert.equal(await complete, false);
  assert.equal(storage.getItem('hxy_technician_token'), t2.token);
  assert.equal(storage.getItem('hxy_admin_token'), null);
  assert.equal(isWecomSession(), false);
});
test('current completion commits one identity and removes the pending attempt', async () => {
  reset();
  globalThis.fetch = async () => reply({ attempt_id: 'a1', authorization_url: 'https://open.weixin.qq.com/connect/oauth2/authorize', expires_in: 300 });
  await beginWecomEntry();
  globalThis.fetch = async () => reply(t2);
  assert.equal(await completeWecomEntry(), true);
  assert.equal(isWecomSession(), true);
  assert.equal(isWecomEntryPending(), false);
  assert.equal(await completeWecomEntry(), false);
});
test('outdated password success cannot resurrect a cleared session', () => {
  reset(); const before = getSessionEpoch(); clearStaffSession();
  assert.equal(commitStaffSession(t1, before), false);
  assert.equal(storage.getItem('hxy_admin_token'), null);
});
test('invalid OAuth redirect never navigates or restores old session', async () => {
  reset(); commitStaffSession(t1, getSessionEpoch());
  globalThis.fetch = async () => reply({ attempt_id: 'a1', authorization_url: 'https://evil.invalid/steal', expires_in: 300 });
  await assert.rejects(beginWecomEntry());
  assert.equal(storage.getItem('hxy_admin_token'), null);
  assert.equal(navigations.length, 0);
});
test('invalid exchange role never commits', async () => {
  reset();
  globalThis.fetch = async () => reply({ attempt_id: 'a1', authorization_url: 'https://open.weixin.qq.com/connect/oauth2/authorize', expires_in: 300 });
  await beginWecomEntry();
  globalThis.fetch = async () => reply({ ...t1, staff: { ...t1.staff, role: 'admin' } });
  await assert.rejects(completeWecomEntry());
  assert.equal(storage.getItem('hxy_admin_token'), null);
});

const managerResponse = {
  token: 'synthetic-manager', auth_method: 'wecom',
  staff: { id: 3, name: 'Synthetic manager', role: 'store_manager', store_id: 1, technician_id: null, store_name: 'Synthetic store' },
  selector_token: null,
  workspaces: [{ assignment_id: 7, role: 'store_manager', scope_type: 'store', scope_id: 1, scope_name: 'Synthetic store' }],
};
async function prepareExchange() {
  reset();
  globalThis.fetch = async () => reply({ attempt_id: 'manager-attempt', authorization_url: 'https://open.weixin.qq.com/connect/oauth2/authorize', expires_in: 300 });
  await beginWecomEntry();
}
test('single-store manager preserves scoped token and uses the existing manager navigation role', async () => {
  await prepareExchange();
  globalThis.fetch = async () => reply(managerResponse);
  assert.equal(await completeWecomEntry(), true);
  assert.equal(storage.getItem('hxy_admin_token'), 'synthetic-manager');
  assert.deepEqual(JSON.parse(storage.getItem('hxy_admin_staff')!), { ...managerResponse.staff, role: 'manager' });
  assert.equal(isWecomSession(), true);
  assert.equal(isWecomEntryPending(), false);
});
test('manager with a technician profile keeps both identities', async () => {
  await prepareExchange();
  const response = { ...managerResponse, staff: { ...managerResponse.staff, technician_id: 12 } };
  globalThis.fetch = async () => reply(response);
  assert.equal(await completeWecomEntry(), true);
  const stored = JSON.parse(storage.getItem('hxy_admin_staff')!);
  assert.equal(stored.role, 'manager');
  assert.equal(stored.technician_id, 12);
});
test('manager exchange rejects missing, ambiguous or inconsistent authorization instead of choosing a workspace', async () => {
  const grant = managerResponse.workspaces[0];
  const variants = [
    { staff: { ...managerResponse.staff, id: 0 } },
    { staff: { ...managerResponse.staff, store_id: 0 } },
    { staff: { ...managerResponse.staff, store_id: null } },
    { staff: { ...managerResponse.staff, technician_id: undefined } },
    ...['manager', 'admin', 'brand_admin', 'hq_operator', 'store_staff', 'unknown'].map(role => ({ staff: { ...managerResponse.staff, role } })),
    { selector_token: 'synthetic-selector' }, { selector_token: undefined },
    { workspaces: undefined }, { workspaces: [] }, { workspaces: [grant, { ...grant, assignment_id: 8 }] },
    { workspaces: [{ ...grant, assignment_id: 0 }] },
    { workspaces: [{ ...grant, role: 'brand_admin' }] },
    { workspaces: [{ ...grant, scope_type: 'brand' }] },
    { workspaces: [{ ...grant, scope_id: 2 }] },
    { workspaces: [null] },
  ];
  for (const [index, change] of variants.entries()) {
    await prepareExchange();
    globalThis.fetch = async () => reply({ ...managerResponse, ...change });
    await assert.rejects(completeWecomEntry(), { message: '企业微信身份响应无效' }, 'Rejected manager variant ' + index);
    assert.equal(storage.getItem('hxy_admin_token'), null);
    assert.equal(storage.getItem('hxy_admin_staff'), null);
  }
});
test('late manager exchange cannot replace a newer technician session', async () => {
  await prepareExchange();
  let resolve!: (response: Response) => void;
  globalThis.fetch = () => new Promise<Response>((done) => { resolve = done; });
  const completing = completeWecomEntry();
  commitStaffSession(t2, getSessionEpoch());
  resolve(reply(managerResponse));
  assert.equal(await completing, false);
  assert.equal(storage.getItem('hxy_technician_token'), t2.token);
  assert.equal(JSON.parse(storage.getItem('hxy_technician_staff')!).role, 'technician');
  assert.equal(storage.getItem('hxy_admin_token'), null);
});

test('manager deep links survive OAuth and choose the store destination', async () => {
  reset();
  tabStorage.setItem('hxy_manager_pending_order', 'synthetic-order-1234');
  assert.equal(hasManagerPendingDeepLink(), true);
  assert.equal(takeManagerPendingOrder(), 'synthetic-order-1234');
  assert.equal(hasManagerPendingDeepLink(), false);
  tabStorage.setItem('hxy_manager_pending_review', JSON.stringify({ type: 'service_review', id: 9 }));
  assert.equal(hasManagerPendingDeepLink(), true);
  assert.deepEqual(takeManagerPendingReview(), { type: 'service_review', id: 9 });
});

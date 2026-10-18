import assert from 'node:assert/strict';
import test from 'node:test';
import { beginWecomEntry, clearStaffSession, commitStaffSession, completeWecomEntry, getSessionEpoch, isWecomEntryPending, isWecomSession, subscribeSessionEpoch } from '../src/wecomSession.ts';

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
Object.assign(globalThis, { window: { location: { origin: 'https://synthetic.invalid', assign: (url: string) => navigations.push(url) }, addEventListener: () => {} } });
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
  assert.equal(storage.getItem('hxy_admin_token'), t2.token);
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

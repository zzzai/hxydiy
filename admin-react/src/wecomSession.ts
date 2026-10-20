import { interpretStaffLogin, type StaffLoginResponse } from './workspaceLogin.ts';
import { ADMIN_TOKEN_KEY, TECHNICIAN_TOKEN_KEY, clearActiveStaffSession, readActiveAuthMethod, readActiveToken, writeStaffSession, browserPathname, isManagerMobilePath, readActiveStaff } from './staffSession.ts';

type StaffSessionResponse = { token: string; staff: object; auth_method?: 'wecom' };
type PendingEntry = { entry_nonce: string; attempt_id?: string; entry_path?: string };
const PENDING_KEY = 'hxy_wecom_pending';
const listeners = new Set<() => void>();
let epoch = 0;
let observedToken: string | null | undefined;

function token(): string | null { return readActiveToken(localStorage); }
function changed(): void {
  observedToken = token();
  epoch += 1;
  for (const listener of [...listeners]) listener();
}
export function getSessionEpoch(): number {
  const current = token();
  if (observedToken === undefined) observedToken = current;
  else if (current !== observedToken) changed();
  return epoch;
}
export function subscribeSessionEpoch(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
export class StaleSessionError extends Error {
  constructor() { super('Session changed'); this.name = 'StaleSessionError'; }
}
export function isStaleSessionError(error: unknown): boolean {
  return error instanceof StaleSessionError;
}
export function isWecomSession(): boolean {
  return Boolean(token()) && readActiveAuthMethod(localStorage) === 'wecom';
}
function pendingEntry(): PendingEntry | null {
  try {
    const pending = JSON.parse(sessionStorage.getItem(PENDING_KEY) || 'null');
    return typeof pending?.entry_nonce === 'string' ? pending : null;
  } catch { return null; }
}
export function isWecomEntryPending(): boolean { return pendingEntry() !== null; }
export function wecomSessionPath(): string {
  return isManagerMobilePath(pendingEntry()?.entry_path || '') ? '/technician/store' : browserPathname();
}
export function clearDepartingWecomSession(preserveSession = false): boolean {
  const path = wecomSessionPath();
  const callbackPending = browserPathname() === '/technician/wecom/complete' && isWecomEntryPending();
  const staff = readActiveStaff(localStorage, path);
  const verified = readActiveToken(localStorage, path) && readActiveAuthMethod(localStorage, path) === 'wecom'
    && ['technician', 'manager'].includes(staff?.role || '');
  if (!callbackPending && !verified) return false;
  if (!preserveSession) clearStaffSession(path);
  return true;
}
export function wecomLoginPath(): '/store/login' | '/login' {
  return isManagerMobilePath(pendingEntry()?.entry_path || browserPathname()) ? '/store/login' : '/login';
}
export function clearStaffSession(pathname = browserPathname()): void {
  clearActiveStaffSession(localStorage, pathname);
  sessionStorage.removeItem(PENDING_KEY);
  changed();
}
export function commitStaffSession(response: StaffSessionResponse, expectedEpoch: number): boolean {
  if (getSessionEpoch() !== expectedEpoch) return false;
  if (!response.token || !response.staff || typeof response.staff !== 'object') throw new Error('登录响应无效');
  writeStaffSession(localStorage, { token: response.token, staff: response.staff, authMethod: response.auth_method });
  sessionStorage.removeItem(PENDING_KEY);
  changed();
  return true;
}
async function post(path: string, body: object): Promise<Record<string, any>> {
  const response = await fetch('/api/v1/auth/wecom/' + path, {
    method: 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = data?.detail;
    throw new Error(typeof detail === 'string' ? detail : detail?.message || '企业微信身份验证失败，请重新进入工作台');
  }
  return data;
}
export async function beginWecomEntry(): Promise<void> {
  const entry_path = browserPathname();
  clearStaffSession();
  const expectedEpoch = getSessionEpoch();
  const entry_nonce = crypto.randomUUID();
  sessionStorage.setItem(PENDING_KEY, JSON.stringify({ entry_nonce, entry_path }));
  try {
    const data = await post('authorize', { entry_nonce });
    if (getSessionEpoch() !== expectedEpoch || pendingEntry()?.entry_nonce !== entry_nonce) return;
    const destination = new URL(data.authorization_url);
    if (destination.origin !== 'https://open.weixin.qq.com' || destination.pathname !== '/connect/oauth2/authorize'
        || typeof data.attempt_id !== 'string' || !data.attempt_id) throw new Error('企业微信登录地址无效');
    sessionStorage.setItem(PENDING_KEY, JSON.stringify({ entry_nonce, attempt_id: data.attempt_id, entry_path }));
    window.location.assign(destination.href);
  } catch (error) {
    if (getSessionEpoch() !== expectedEpoch || pendingEntry()?.entry_nonce !== entry_nonce) return;
    sessionStorage.removeItem(PENDING_KEY);
    throw error;
  }
}
export async function completeWecomEntry(onAccepted?: (role: 'technician' | 'manager') => void): Promise<boolean> {
  const pending = pendingEntry();
  if (!pending?.attempt_id) return false;
  const expectedEpoch = getSessionEpoch();
  let data: Record<string, any>;
  try { data = await post('exchange', { entry_nonce: pending.entry_nonce, attempt_id: pending.attempt_id }); }
  catch (error) {
    if (getSessionEpoch() !== expectedEpoch || pendingEntry()?.entry_nonce !== pending.entry_nonce) return false;
    throw error;
  }
  if (getSessionEpoch() !== expectedEpoch || pendingEntry()?.entry_nonce !== pending.entry_nonce) return false;
  if (data.auth_method !== 'wecom' || !Number.isInteger(data.staff?.id)
      || !Number.isInteger(data.staff?.store_id) || data.staff.store_id <= 0
      || typeof data.token !== 'string' || !data.token) {
    throw new Error('企业微信身份响应无效');
  }
  if (data.staff.role === 'technician') {
    if (!Number.isInteger(data.staff.technician_id) || data.staff.technician_id <= 0) {
      throw new Error('企业微信身份响应无效');
    }
    const accepted = commitStaffSession(data as StaffSessionResponse, expectedEpoch);
    if (accepted) onAccepted?.('technician');
    return accepted;
  }
  const workspace = Array.isArray(data.workspaces) && data.workspaces.length === 1 ? data.workspaces[0] : null;
  if (data.staff.role !== 'store_manager' || data.staff.id <= 0 || data.staff.technician_id !== null
      || data.selector_token !== null || !Number.isInteger(workspace?.assignment_id) || workspace.assignment_id <= 0
      || workspace.role !== 'store_manager' || workspace.scope_type !== 'store' || workspace.scope_id !== data.staff.store_id) {
    throw new Error('企业微信身份响应无效');
  }
  const session = interpretStaffLogin(data as StaffLoginResponse);
  if (session.kind !== 'ready' || session.staff.role !== 'manager') throw new Error('企业微信身份响应无效');
  const accepted = commitStaffSession({ token: session.token, staff: session.staff, auth_method: 'wecom' }, expectedEpoch);
  if (accepted) onAccepted?.('manager');
  return accepted;
}
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (event: StorageEvent) => {
    if (event.key === ADMIN_TOKEN_KEY || event.key === TECHNICIAN_TOKEN_KEY || event.key === null) getSessionEpoch();
  });
}

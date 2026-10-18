type StaffSessionResponse = { token: string; staff: object; auth_method?: 'wecom' };
type PendingEntry = { entry_nonce: string; attempt_id?: string };
const PENDING_KEY = 'hxy_wecom_pending';
const METHOD_KEY = 'hxy_staff_auth_method';
const listeners = new Set<() => void>();
let epoch = 0;
let observedToken: string | null | undefined;

function token(): string | null { return localStorage.getItem('hxy_admin_token'); }
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
  return Boolean(token()) && localStorage.getItem(METHOD_KEY) === 'wecom';
}
function pendingEntry(): PendingEntry | null {
  try {
    const pending = JSON.parse(sessionStorage.getItem(PENDING_KEY) || 'null');
    return typeof pending?.entry_nonce === 'string' ? pending : null;
  } catch { return null; }
}
export function isWecomEntryPending(): boolean { return pendingEntry() !== null; }
export function clearStaffSession(): void {
  localStorage.removeItem('hxy_admin_token');
  localStorage.removeItem('hxy_admin_staff');
  localStorage.removeItem(METHOD_KEY);
  sessionStorage.removeItem(PENDING_KEY);
  changed();
}
export function commitStaffSession(response: StaffSessionResponse, expectedEpoch: number): boolean {
  if (getSessionEpoch() !== expectedEpoch) return false;
  if (!response.token || !response.staff || typeof response.staff !== 'object') throw new Error('登录响应无效');
  localStorage.setItem('hxy_admin_staff', JSON.stringify(response.staff));
  localStorage.setItem('hxy_admin_token', response.token);
  if (response.auth_method === 'wecom') localStorage.setItem(METHOD_KEY, 'wecom');
  else localStorage.removeItem(METHOD_KEY);
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
  clearStaffSession();
  const expectedEpoch = getSessionEpoch();
  const entry_nonce = crypto.randomUUID();
  sessionStorage.setItem(PENDING_KEY, JSON.stringify({ entry_nonce }));
  try {
    const data = await post('authorize', { entry_nonce });
    if (getSessionEpoch() !== expectedEpoch || pendingEntry()?.entry_nonce !== entry_nonce) return;
    const destination = new URL(data.authorization_url);
    if (destination.origin !== 'https://open.weixin.qq.com' || destination.pathname !== '/connect/oauth2/authorize'
        || typeof data.attempt_id !== 'string' || !data.attempt_id) throw new Error('企业微信登录地址无效');
    sessionStorage.setItem(PENDING_KEY, JSON.stringify({ entry_nonce, attempt_id: data.attempt_id }));
    window.location.assign(destination.href);
  } catch (error) {
    if (getSessionEpoch() !== expectedEpoch || pendingEntry()?.entry_nonce !== entry_nonce) return;
    sessionStorage.removeItem(PENDING_KEY);
    throw error;
  }
}
export async function completeWecomEntry(): Promise<boolean> {
  const pending = pendingEntry();
  if (!pending?.attempt_id) return false;
  const expectedEpoch = getSessionEpoch();
  let data: Record<string, any>;
  try { data = await post('exchange', pending); }
  catch (error) {
    if (getSessionEpoch() !== expectedEpoch || pendingEntry()?.entry_nonce !== pending.entry_nonce) return false;
    throw error;
  }
  if (getSessionEpoch() !== expectedEpoch || pendingEntry()?.entry_nonce !== pending.entry_nonce) return false;
  if (data.auth_method !== 'wecom' || data.staff?.role !== 'technician' || !Number.isInteger(data.staff?.id)
      || !Number.isInteger(data.staff?.store_id) || !Number.isInteger(data.staff?.technician_id)
      || data.staff.store_id <= 0 || data.staff.technician_id <= 0 || typeof data.token !== 'string' || !data.token) {
    throw new Error('企业微信身份响应无效');
  }
  return commitStaffSession(data as StaffSessionResponse, expectedEpoch);
}
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (event: StorageEvent) => {
    if (event.key === 'hxy_admin_token' || event.key === null) getSessionEpoch();
  });
}

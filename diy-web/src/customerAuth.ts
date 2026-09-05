export type CustomerUser = {
  id: number;
  openid: string;
  phone: string;
  nickname: string;
  is_member: boolean;
  member_type: string | null;
  member_expire_at?: string | null;
  balance_cents: number;
};

export type CustomerAuth = { token: string; user: CustomerUser };

const STORAGE_KEY = 'hxy_diy_customer_auth';
export const CUSTOMER_SESSION_REFRESH_INTERVAL_MS = 5_000;

export function normalizePhone(value: string): string {
  return value.replace(/\D/g, '').slice(0, 11);
}

export function isValidPhone(value: string): boolean {
  return /^1[3-9]\d{9}$/.test(normalizePhone(value));
}

export function readCustomerAuth(): CustomerAuth | null {
  try {
    const auth = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null') as CustomerAuth | null;
    if (!auth) return null;
    if (isCustomerAuthTokenActive(auth.token)) return auth;
    clearCustomerAuth();
    return null;
  } catch {
    clearCustomerAuth();
    return null;
  }
}

export function writeCustomerAuth(auth: CustomerAuth) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(auth));
}

export function clearCustomerAuth() {
  localStorage.removeItem(STORAGE_KEY);
}

export function isCustomerAuthTokenActive(token: string, nowSeconds = Math.floor(Date.now() / 1000)): boolean {
  try {
    const payload = token.split('.')[1];
    if (!payload) return false;
    const decoded = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(payload.length / 4) * 4, '='))) as { exp?: unknown };
    return typeof decoded.exp === 'number' && decoded.exp > nowSeconds;
  } catch {
    return false;
  }
}

export function authFailureAction(error: unknown): 'session-replaced' | 'reauthenticate' | 'show-error' {
  if (typeof error !== 'object' || error === null || !('status' in error) || (error as { status?: unknown }).status !== 401) return 'show-error';
  return 'code' in error && (error as { code?: unknown }).code === 'SESSION_REPLACED' ? 'session-replaced' : 'reauthenticate';
}

export function shouldOfferRecordBinding(evaluated: boolean, auth: CustomerAuth | null): boolean {
  return evaluated && !auth;
}

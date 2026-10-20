export const ADMIN_TOKEN_KEY = 'hxy_admin_token';
export const ADMIN_STAFF_KEY = 'hxy_admin_staff';
export const ADMIN_AUTH_METHOD_KEY = 'hxy_staff_auth_method';
export const TECHNICIAN_TOKEN_KEY = 'hxy_technician_token';
export const TECHNICIAN_STAFF_KEY = 'hxy_technician_staff';
export const TECHNICIAN_AUTH_METHOD_KEY = 'hxy_technician_auth_method';

export type SessionSlot = 'admin' | 'technician';
type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
export type StoredStaff = {
  id?: number;
  name?: string;
  role?: string;
  store_id?: number | null;
  technician_id?: number | null;
  store_name?: string;
};

const SLOT_KEYS = {
  admin: { token: ADMIN_TOKEN_KEY, staff: ADMIN_STAFF_KEY, method: ADMIN_AUTH_METHOD_KEY },
  technician: { token: TECHNICIAN_TOKEN_KEY, staff: TECHNICIAN_STAFF_KEY, method: TECHNICIAN_AUTH_METHOD_KEY },
} as const;

export function isTechnicianPath(pathname: string): boolean {
  return pathname === '/technician' || pathname.startsWith('/technician/');
}

export function browserPathname(): string {
  try {
    return window.location?.pathname || '';
  } catch {
    return '';
  }
}

function readStaff(storage: StorageLike, key: string): StoredStaff | null {
  try {
    const raw = storage.getItem(key);
    return raw ? JSON.parse(raw) as StoredStaff : null;
  } catch {
    return null;
  }
}

export function migrateLegacyTechnicianSession(storage: StorageLike): boolean {
  const staff = readStaff(storage, ADMIN_STAFF_KEY);
  if (staff?.role !== 'technician') return false;
  const token = storage.getItem(ADMIN_TOKEN_KEY);
  const rawStaff = storage.getItem(ADMIN_STAFF_KEY);
  if (token && rawStaff && !storage.getItem(TECHNICIAN_TOKEN_KEY)) {
    storage.setItem(TECHNICIAN_TOKEN_KEY, token);
    storage.setItem(TECHNICIAN_STAFF_KEY, rawStaff);
    const method = storage.getItem(ADMIN_AUTH_METHOD_KEY);
    if (method) storage.setItem(TECHNICIAN_AUTH_METHOD_KEY, method);
  }
  storage.removeItem(ADMIN_TOKEN_KEY);
  storage.removeItem(ADMIN_STAFF_KEY);
  storage.removeItem(ADMIN_AUTH_METHOD_KEY);
  return true;
}

export function activeSessionSlot(storage: StorageLike, pathname: string): SessionSlot {
  migrateLegacyTechnicianSession(storage);
  if (!isTechnicianPath(pathname)) return 'admin';
  if (readStaff(storage, TECHNICIAN_STAFF_KEY)?.role === 'technician') return 'technician';
  const adminRole = readStaff(storage, ADMIN_STAFF_KEY)?.role;
  if (adminRole && adminRole !== 'technician') return 'admin';
  return 'technician';
}

export function readActiveToken(storage: StorageLike, pathname = browserPathname()): string {
  const keys = SLOT_KEYS[activeSessionSlot(storage, pathname)];
  return storage.getItem(keys.token) || '';
}

export function readActiveStaff(storage: StorageLike, pathname = browserPathname()): StoredStaff | null {
  const keys = SLOT_KEYS[activeSessionSlot(storage, pathname)];
  return readStaff(storage, keys.staff);
}

export function readActiveAuthMethod(storage: StorageLike, pathname = browserPathname()): string | null {
  const keys = SLOT_KEYS[activeSessionSlot(storage, pathname)];
  return storage.getItem(keys.method);
}

export function writeStaffSession(storage: StorageLike, session: { token: string; staff: object; authMethod?: string | null }): void {
  const role = (session.staff as StoredStaff)?.role;
  const keys = SLOT_KEYS[role === 'technician' ? 'technician' : 'admin'];
  storage.setItem(keys.token, session.token);
  storage.setItem(keys.staff, JSON.stringify(session.staff));
  if (session.authMethod === 'wecom') storage.setItem(keys.method, 'wecom');
  else storage.removeItem(keys.method);
}

export function clearActiveStaffSession(storage: StorageLike, pathname = browserPathname()): void {
  const keys = SLOT_KEYS[activeSessionSlot(storage, pathname)];
  storage.removeItem(keys.token);
  storage.removeItem(keys.staff);
  storage.removeItem(keys.method);
}

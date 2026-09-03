import { getNavigationPaths, isNavigationPathAllowed } from './core/navigation/index.ts';

export type StaffRole = 'admin' | 'manager' | 'staff' | 'technician';

export type StaffContext = {
  role?: string;
  store_id?: number | null;
};

const TECHNICIAN_PATHS = ['/technician'] as const;

export function isTechnicianEntry(pathname: string = window.location.pathname): boolean {
  return pathname === '/technician' || pathname.startsWith('/technician/');
}

export function getEntryLoginPath(technicianEntry: boolean): string {
  return technicianEntry ? '/technician/login' : '/admin/#/login';
}

export function getEntryHomePath(technicianEntry: boolean): string {
  return technicianEntry ? '/technician/today' : '/admin/#/';
}

export function getPostLoginRedirect(pathname: string, role?: string): string {
  const technicianEntry = isTechnicianEntry(pathname);
  if (role === 'technician') return '/technician/today';
  return technicianEntry ? '/admin/#/today' : '/admin/#/';
}
export function getVisibleMenuPaths(role?: string, storeId?: number | null): string[] {
  if (role === 'technician') return [...TECHNICIAN_PATHS];
  return getNavigationPaths(role, storeId);
}

export function isPathAllowed(role: string | undefined, pathname: string, storeId?: number | null): boolean {
  if (role === 'technician') return TECHNICIAN_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`));
  return isNavigationPathAllowed(role, pathname, storeId);
}

export function getDefaultPath(role?: string, storeId?: number | null): string {
  return getVisibleMenuPaths(role, storeId)[0] || '/forbidden';
}

export function canManageConfiguration(role?: string): boolean {
  return role === 'admin' || role === 'manager';
}

export function canManageStoreMasterData(role?: string, storeId?: number | null): boolean {
  return role === 'admin' && !storeId;
}

export function getStoreId(staff: StaffContext | null | undefined): number {
  if (!staff?.store_id || staff.store_id < 1) {
    throw new Error('当前账号未绑定门店，无法执行此操作');
  }
  return staff.store_id;
}

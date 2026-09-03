export const ADMIN_TOKEN_KEY = 'hxy_admin_token';
export const ADMIN_STAFF_KEY = 'hxy_admin_staff';

export type AuthStaff = { role?: string; store_id?: number | null };

export function clearAuthSession() {
  localStorage.removeItem(ADMIN_TOKEN_KEY);
  localStorage.removeItem(ADMIN_STAFF_KEY);
}

export function redirectToLogin() {
  if (window.location.pathname === '/technician' || window.location.pathname.startsWith('/technician/')) {
    window.location.replace('/technician/login');
    return;
  }
  window.location.hash = '#/login';
}

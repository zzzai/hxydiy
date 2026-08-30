export type Permission = 'manage_configuration' | 'manage_store_master_data';

export function hasPermission(role: string | undefined, permission: Permission, storeId?: number | null): boolean {
  if (permission === 'manage_configuration') return role === 'admin' || role === 'manager';
  return role === 'admin' && !storeId;
}

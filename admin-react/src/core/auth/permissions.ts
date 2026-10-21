import { hasCapability } from './capabilities.ts';

export type Permission = 'manage_configuration' | 'manage_store_master_data';

export function hasPermission(role: string | undefined, permission: Permission, storeId?: number | null): boolean {
  if (permission === 'manage_configuration') return hasCapability(role, 'manage_store_resources', storeId);
  return hasCapability(role, 'manage_headquarters', storeId);
}

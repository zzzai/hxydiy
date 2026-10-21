export const CAPABILITY_KEYS = [
  'self_service',
  'view_store_operations',
  'manage_store_resources',
  'manage_technicians',
  'toggle_catalog_publication',
  'manage_catalog_master',
  'follow_up_reviews',
  'view_analytics',
  'manage_customer_tags',
  'manage_marketing',
  'manage_automation',
  'manage_staff_accounts',
  'manage_headquarters',
] as const;

export type Capability = typeof CAPABILITY_KEYS[number];

const manager: Record<Capability, boolean> = {
  self_service: false,
  view_store_operations: true,
  manage_store_resources: true,
  manage_technicians: true,
  toggle_catalog_publication: true,
  manage_catalog_master: false,
  follow_up_reviews: true,
  view_analytics: true,
  manage_customer_tags: true,
  manage_marketing: false,
  manage_automation: false,
  manage_staff_accounts: false,
  manage_headquarters: false,
};

const all = Object.fromEntries(CAPABILITY_KEYS.map(key => [key, true])) as Record<Capability, boolean>;
const none = Object.fromEntries(CAPABILITY_KEYS.map(key => [key, false])) as Record<Capability, boolean>;

export function capabilitiesFor(role?: string, storeId?: number | null, technicianId?: number | null): Record<Capability, boolean> {
  if (role === 'admin' && !storeId) return { ...all, self_service: false };
  if ((role === 'admin' || role === 'manager') && storeId) return { ...manager };
  if (role === 'technician' && storeId && technicianId) return { ...none, self_service: true };
  if (role === 'staff' && storeId) return { ...none, view_store_operations: true };
  return { ...none };
}

export function hasCapability(role: string | undefined, capability: Capability, storeId?: number | null, technicianId?: number | null): boolean {
  return capabilitiesFor(role, storeId, technicianId)[capability];
}

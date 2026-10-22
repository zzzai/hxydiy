export type StoreStatus = 'preparing' | 'trial_open' | 'open' | 'suspended' | 'closed';

export type Store = {
  id: number;
  store_code: string;
  name: string;
  city: string;
  address: string;
  phone: string;
  business_hours: string;
  status: StoreStatus;
};

const STATUS_META: Record<StoreStatus, { label: string; color: string }> = {
  preparing: { label: '筹备中', color: 'gold' },
  trial_open: { label: '试营业', color: 'green' },
  open: { label: '营业中', color: 'green' },
  suspended: { label: '暂停营业', color: 'orange' },
  closed: { label: '已停业', color: 'default' },
};

const STORE_TRANSITIONS: Record<StoreStatus, StoreStatus[]> = {
  preparing: ['preparing', 'trial_open', 'open', 'closed'],
  trial_open: ['trial_open', 'open', 'suspended', 'closed'],
  open: ['open', 'suspended', 'closed'],
  suspended: ['suspended', 'open', 'closed'],
  closed: ['closed'],
};

export const STORE_STATUS_OPTIONS: { value: StoreStatus; label: string }[] = [
  { value: 'preparing', label: '筹备中' },
  { value: 'trial_open', label: '试营业' },
  { value: 'open', label: '营业中' },
  { value: 'suspended', label: '暂停营业' },
  { value: 'closed', label: '已停业' },
];

export function getStoreStatusOptions(current?: StoreStatus) {
  if (!current) return STORE_STATUS_OPTIONS;
  const allowed = new Set(STORE_TRANSITIONS[current] || [current]);
  return STORE_STATUS_OPTIONS.filter((option) => allowed.has(option.value));
}

export function getStoreStatusMeta(status: StoreStatus) {
  return STATUS_META[status] || STATUS_META.preparing;
}

export function normalizeStoreList(result: { data: Store[]; total: number }) {
  return { data: result.data, total: result.total };
}

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

export function getStoreStatusMeta(status: StoreStatus) {
  return STATUS_META[status] || STATUS_META.preparing;
}

export function normalizeStoreList(result: { data: Store[]; total: number }) {
  return { data: result.data, total: result.total };
}

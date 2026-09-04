export type Addon = {
  id: number;
  store_id: number;
  code: string;
  name: string;
  parent_project_id?: number | null;
  duration_min?: number | null;
  summary?: string;
  image_url?: string;
  display_order?: number;
  chargeable: boolean;
  store_price_cents: number;
  member_price_cents?: number | null;
  member_price_enabled: boolean;
  independently_sellable: boolean;
  can_attach_to_parent: boolean;
  publication_status: string;
};

export const ADDON_STATUS_OPTIONS = [
  { value: 'draft', label: '草稿' },
  { value: 'candidate', label: '待发布' },
  { value: 'published', label: '已上架' },
  { value: 'inactive', label: '已下架' },
  { value: 'archived', label: '总部强制下线' },
] as const;

const STORE_TOGGLEABLE_STATUSES = new Set(['candidate', 'published', 'inactive']);

export function canViewAddons(role?: string) {
  return role === 'admin' || role === 'manager';
}

export function isHeadquartersAddonAdmin(role?: string, storeId?: number | null) {
  return role === 'admin' && !storeId;
}

export function canEditAddonMasterData(role?: string, storeId?: number | null) {
  return isHeadquartersAddonAdmin(role, storeId);
}

export function canStoreToggleAddon(status: string) {
  return STORE_TOGGLEABLE_STATUSES.has(status);
}

export function addonStatusColor(status: string) {
  if (status === 'published') return 'green';
  if (status === 'inactive') return 'red';
  if (status === 'archived') return 'default';
  return 'gold';
}

export function addonStatusLabel(status: string) {
  return ADDON_STATUS_OPTIONS.find((item) => item.value === status)?.label || status;
}

export function normalizeAddonList(result: unknown): { data: Addon[]; total: number } {
  if (Array.isArray(result)) return { data: result as Addon[], total: result.length };
  const value = result as { data?: Addon[]; items?: Addon[]; total?: number } | null;
  const data = value?.data || value?.items || [];
  return { data, total: Number(value?.total ?? data.length) };
}

export function addonCreateStoreId(role: string | undefined, boundStoreId: number | null | undefined, targetStoreId: number | null | undefined) {
  if (isHeadquartersAddonAdmin(role, boundStoreId)) {
    if (!targetStoreId || targetStoreId < 1) throw new Error('请选择目标门店');
    return targetStoreId;
  }
  if (!boundStoreId || boundStoreId < 1) throw new Error('当前账号未绑定门店，无法执行此操作');
  return boundStoreId;
}

export function validateAddonPrices(values: { chargeable?: boolean; store_price?: number | null; member_price_enabled?: boolean; member_price?: number | null }) {
  if (values.chargeable === false) return null;
  if (values.store_price == null || !Number.isFinite(Number(values.store_price)) || Number(values.store_price) < 0) return '请填写有效的门店价';
  if (values.member_price_enabled === true && (values.member_price == null || !Number.isFinite(Number(values.member_price)) || Number(values.member_price) < 0)) return '启用会员价时请填写有效的会员价';
  if (values.member_price_enabled === true && Number(values.member_price) > Number(values.store_price)) return '会员价不能高于门店价';
  return null;
}

export function addonToFormValues(addon: Addon) {
  return {
    ...addon,
    store_price: Number(addon.store_price_cents || 0) / 100,
    member_price: addon.member_price_enabled ? Number(addon.member_price_cents || 0) / 100 : null,
  };
}

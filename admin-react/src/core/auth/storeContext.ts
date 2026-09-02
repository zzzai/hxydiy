export type StoreContext = { storeId: number | null };

export type StoreContextStaff = {
  role?: string;
  store_id?: number | null;
  store_name?: string | null;
};

export function getStoreContextLabel(staff?: StoreContextStaff | null): string {
  if (staff?.store_name) return staff.store_name;
  if (staff?.store_id) return '当前门店';
  return '总部';
}

export function requireStoreId(context: StoreContext): number {
  if (!context.storeId || context.storeId < 1) throw new Error('当前账号未绑定门店，无法执行此操作');
  return context.storeId;
}

export function withBoundStore<T extends Record<string, unknown>>(
  input: T,
  storeId: number | null,
): Omit<T, 'store_id'> & { store_id?: number } {
  const { store_id: _ignored, ...rest } = input;
  return storeId ? { ...rest, store_id: storeId } : rest;
}

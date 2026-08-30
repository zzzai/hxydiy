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
): Record<string, unknown> {
  // 总部没有绑定门店时，目录创建的目标门店由调用方显式提供，仍由服务端鉴权。
  if (!storeId) return input;
  const { store_id: _ignored, ...rest } = input;
  return { ...rest, store_id: storeId };
}

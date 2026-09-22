export type Product = {
  id: number;
  store_id: number;
  code: string;
  name: string;
  desc?: string;
  spec?: string;
  product_type: string;
  price_cents: number;
  member_price_cents?: number | null;
  member_price_enabled?: boolean;
  image_url?: string;
  detail_modules?: Array<{ type?: string; title?: string; body?: string }>;
  display_order?: number;
  publication_status: string;
};

export const PRODUCT_TYPE_OPTIONS = [
  { value: 'foot', label: '泡脚包' },
  { value: 'heat', label: '热敷' },
  { value: 'gift', label: '礼盒' },
];

export const PRODUCT_TYPE_LABELS = Object.fromEntries(
  PRODUCT_TYPE_OPTIONS.map((option) => [option.value, option.label]),
) as Record<string, string>;

const STORE_TOGGLEABLE_PRODUCT_STATUSES = new Set(['candidate', 'published', 'inactive']);

export function canStoreToggleProductPublication(status: string) {
  return STORE_TOGGLEABLE_PRODUCT_STATUSES.has(status);
}

export function formatProductPrice(priceCents: number) {
  return `¥${(Number(priceCents || 0) / 100).toFixed(2)}`;
}

export function normalizeProductList(result: unknown) {
  if (Array.isArray(result)) return { data: result as Product[], total: result.length };
  const value = result as { data?: Product[]; items?: Product[]; total?: number };
  const data = value?.data || value?.items || [];
  return { data, total: Number(value?.total ?? data.length) };
}

export function productToForm(product: Product) {
  return {
    code: product.code,
    name: product.name,
    desc: product.desc || '',
    spec: product.spec || '',
    product_type: product.product_type,
    price: Number((Number(product.price_cents || 0) / 100).toFixed(2)),
    member_price_enabled: Boolean(product.member_price_enabled),
    member_price: product.member_price_enabled && product.member_price_cents !== null && product.member_price_cents !== undefined
      ? Number((Number(product.member_price_cents) / 100).toFixed(2))
      : undefined,
    image_url: product.image_url || '',
    detail_modules: product.detail_modules || [],
    display_order: Number(product.display_order || 0),
    publication_status: product.publication_status,
  };
}

export function toProductPayload(values: Record<string, unknown>, storeId: number) {
  const { price, member_price, member_price_enabled, ...rest } = values as {
    price?: number;
    member_price?: number;
    member_price_enabled?: boolean;
  } & Record<string, unknown>;
  const hasMemberPriceConfiguration = Object.hasOwn(values, 'member_price_enabled');
  return {
    ...rest,
    store_id: storeId,
    price_cents: Math.round(Number(price ?? 0) * 100),
    image_url: values.image_url || '',
    ...(hasMemberPriceConfiguration
      ? {
        member_price_enabled: Boolean(member_price_enabled),
        member_price_cents: member_price_enabled ? Math.round(Number(member_price ?? 0) * 100) : null,
      }
      : {}),
  };
}

export function toProductUpdatePayload(values: Record<string, unknown>) {
  const { store_id: _storeId, ...payload } = toProductPayload(values, 0);
  return payload;
}

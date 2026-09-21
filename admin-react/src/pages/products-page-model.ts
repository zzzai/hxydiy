import type { components } from '../generated/openapi';

export type Product = components['schemas']['AdminProduct'];

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
  const textModule = product.detail_modules?.find((module) => module.type === 'text');
  return {
    code: product.code,
    name: product.name,
    desc: product.desc || '',
    spec: product.spec || '',
    product_type: product.product_type,
    price: Number((Number(product.price_cents || 0) / 100).toFixed(2)),
    member_price: product.member_price_cents == null
      ? undefined
      : Number((Number(product.member_price_cents) / 100).toFixed(2)),
    image_url: product.image_url || '',
    display_order: product.display_order || 0,
    detail_text: textModule?.body || '',
    publication_status: product.publication_status,
  };
}

export function toProductPayload(values: Record<string, unknown>, storeId: number) {
  const {
    price,
    member_price: memberPrice,
    detail_text: detailText,
    ...rest
  } = values as { price?: number; member_price?: number | null; detail_text?: string } & Record<string, unknown>;
  return {
    ...rest,
    store_id: storeId,
    price_cents: Math.round(Number(price ?? 0) * 100),
    ...(Object.prototype.hasOwnProperty.call(values, 'member_price')
      ? { member_price_cents: memberPrice == null ? null : Math.round(Number(memberPrice) * 100) }
      : {}),
    ...(Object.prototype.hasOwnProperty.call(values, 'detail_text')
      ? { detail_modules: detailText?.trim() ? [{ type: 'text', body: detailText.trim() }] : [] }
      : {}),
    image_url: values.image_url || '',
  };
}

export function toProductUpdatePayload(values: Record<string, unknown>) {
  const { store_id: _storeId, ...payload } = toProductPayload(values, 0);
  return payload;
}

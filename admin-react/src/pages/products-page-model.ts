export type Product = {
  id: number;
  store_id: number;
  code: string;
  name: string;
  desc?: string;
  spec?: string;
  product_type: string;
  price_cents: number;
  image_url?: string;
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
    image_url: product.image_url || '',
    publication_status: product.publication_status,
  };
}

export function toProductPayload(values: Record<string, unknown>, storeId: number) {
  const { price, ...rest } = values as { price?: number } & Record<string, unknown>;
  return {
    ...rest,
    store_id: storeId,
    price_cents: Math.round(Number(price ?? 0) * 100),
    image_url: values.image_url || '',
  };
}

export function toProductUpdatePayload(values: Record<string, unknown>) {
  const { store_id: _storeId, ...payload } = toProductPayload(values, 0);
  return payload;
}

export type Project = {
  id: number;
  store_id: number;
  code: string;
  category: string;
  category_mark?: string;
  name: string;
  duration_min?: number | null;
  summary?: string;
  image_url?: string;
  tags?: string[];
  detail_modules?: unknown[];
  diy_options?: unknown[];
  display_order?: number;
  price_label?: string;
  publication_status: string;
  prices?: Record<string, number>;
};

export const CATEGORY_OPTIONS = [
  { value: 'bath', label: '泡脚沐足' },
  { value: 'balance', label: '推拿' },
  { value: 'care', label: '精油SPA' },
  { value: 'small', label: '养生小项' },
  { value: 'local-strength', label: '局部调理' },
  { value: 'kit', label: '功夫调理' },
  { value: 'tea', label: '茶饮' },
] as const;

export const PROJECT_STATUS_OPTIONS = [
  { value: 'draft', label: '草稿' },
  { value: 'candidate', label: '待审核' },
  { value: 'published', label: '已发布' },
  { value: 'inactive', label: '已停用' },
  { value: 'archived', label: '已归档' },
] as const;

export const CATEGORY_LABELS = Object.fromEntries(
  CATEGORY_OPTIONS.map((item) => [item.value, item.label]),
) as Record<string, string>;

export const PROJECT_STATUS_LABELS = Object.fromEntries(
  PROJECT_STATUS_OPTIONS.map((item) => [item.value, item.label]),
) as Record<string, string>;

export function normalizeProjectList(result: unknown): { data: Project[]; total: number } {
  if (Array.isArray(result)) return { data: result as Project[], total: result.length };
  const value = result as { data?: Project[]; items?: Project[]; total?: number } | null;
  const data = value?.data || value?.items || [];
  return { data, total: Number(value?.total ?? data.length) };
}

export function formatProjectPrice(priceCents: number | null | undefined): string {
  return typeof priceCents === 'number' && Number.isFinite(priceCents)
    ? `¥${(priceCents / 100).toFixed(2)}`
    : '-';
}

export function projectFilterParams(filters: { publication_status?: string; category?: string }) {
  return {
    ...(filters.publication_status ? { status: filters.publication_status } : {}),
    ...(filters.category ? { category: filters.category } : {}),
  };
}

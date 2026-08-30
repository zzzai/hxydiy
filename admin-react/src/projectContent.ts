export type ProjectFormValues = {
  category?: string;
  code?: string;
  tags_text?: string;
  store_price?: number;
  member_price?: number;
  group_price?: number;
  detail_modules?: unknown[];
  diy_options?: unknown[];
  [key: string]: unknown;
};

// 历史误分类仍为套盒的稳定编码。
const DETAIL_ONLY_CODES = new Set(['hxy-taoke-60']);

export function supportsDiyOptions(category: string | undefined, code?: string): boolean {
  if (category === 'kit') return false;
  if (code && DETAIL_ONLY_CODES.has(code)) return false;
  return true;
}

export function projectFormPayload(values: ProjectFormValues) {
  const { tags_text, store_price, member_price, group_price, ...rest } = values;
  const prices: Record<string, number> = {};
  if (store_price !== undefined) prices.store = Math.round(store_price * 100);
  if (member_price !== undefined) prices.member = Math.round(member_price * 100);
  if (group_price !== undefined) prices.group = Math.round(group_price * 100);
  return {
    ...rest,
    tags: (tags_text || '').split(/[，,]/).map((item) => item.trim()).filter(Boolean),
    detail_modules: values.detail_modules || [],
    diy_options: supportsDiyOptions(String(values.category || ''), values.code) ? values.diy_options || [] : [],
    prices,
  };
}

export function projectToForm(project: any) {
  return {
    ...project,
    tags_text: (project.tags || []).join('，'),
    store_price: project.prices?.store === undefined ? undefined : project.prices.store / 100,
    member_price: project.prices?.member === undefined ? undefined : project.prices.member / 100,
    group_price: project.prices?.group === undefined ? undefined : project.prices.group / 100,
  };
}

export type ContentRow = Record<string, unknown> & { _original?: Record<string, unknown> };
export type PageContentForm = {
  title: string;
  subtitle: string;
  published: boolean;
  promo_banners: ContentRow[];
  tea_options: ContentRow[];
  coupon_prompt: ContentRow;
  brand_story: ContentRow;
};

const rowFields = {
  promo_banners: ['eyebrow', 'title'],
  tea_options: ['name', 'note', 'description', 'image_url'],
  coupon_prompt: ['title', 'body'],
  brand_story: ['title', 'body', 'image_url'],
} as const;

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('历史内容格式暂不支持编辑，请联系管理员核对；原内容未修改。');
  return value as Record<string, unknown>;
}

function rowToForm(value: unknown, keys: readonly string[]): ContentRow {
  const source = object(value);
  const row: ContentRow = { _original: structuredClone(source) };
  for (const key of keys) {
    if (source[key] !== undefined && source[key] !== null && typeof source[key] !== 'string') throw new Error('历史内容格式暂不支持编辑，请联系管理员核对；原内容未修改。');
    row[key] = source[key] ?? '';
  }
  return row;
}

export function pageContentToForm(value: unknown): PageContentForm {
  const source = object(value);
  if (typeof source.title !== 'string' || typeof source.subtitle !== 'string' || typeof source.published !== 'boolean') throw new Error('页面内容格式不完整，暂不能编辑，请重新加载。');
  const rows = (key: 'promo_banners' | 'tea_options') => {
    if (!Array.isArray(source[key])) throw new Error('历史内容格式暂不支持编辑，请联系管理员核对；原内容未修改。');
    return (source[key] as unknown[]).map(row => rowToForm(row, rowFields[key]));
  };
  return { title: source.title, subtitle: source.subtitle, published: source.published,
    promo_banners: rows('promo_banners'), tea_options: rows('tea_options'),
    coupon_prompt: rowToForm(source.coupon_prompt, rowFields.coupon_prompt),
    brand_story: rowToForm(source.brand_story, rowFields.brand_story) };
}

function rowPayload(value: ContentRow, keys: readonly string[]) {
  const result = { ...value._original };
  for (const key of keys) {
    const field = value[key];
    if (field !== undefined && field !== null && typeof field !== 'string') throw new Error('请检查文字内容。');
    // Keep absent/null historical fields unchanged until the operator edits them.
    if ((field ?? '') !== '' || result[key] !== undefined && result[key] !== null) result[key] = field ?? '';
  }
  return result;
}

export function pageContentPayload(form: PageContentForm) {
  if (!form.title?.trim()) throw new Error('请填写页面配置标题。');
  return {
    title: form.title, subtitle: form.subtitle ?? '', published: form.published === true,
    promo_banners: (form.promo_banners ?? []).map(row => rowPayload(row, rowFields.promo_banners)),
    tea_options: (form.tea_options ?? []).map(row => rowPayload(row, rowFields.tea_options)),
    coupon_prompt: rowPayload(form.coupon_prompt, rowFields.coupon_prompt),
    brand_story: rowPayload(form.brand_story, rowFields.brand_story),
  };
}

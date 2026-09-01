export type ChoiceType = 'preference' | 'linked_project' | 'dedicated_charge';
export type ChargeMode = 'free' | 'inherit_linked_price' | 'custom_price';
export type PriceType = 'store' | 'group' | 'member';

export type OptionGroupForm = {
  code?: string;
  name?: string;
  description?: string;
  selection_mode?: 'single' | 'multiple';
  required?: boolean;
  min_select?: number;
  max_select?: number;
  display_order?: number;
};

export type OptionChoiceForm = {
  code?: string;
  name?: string;
  description?: string;
  choice_type?: ChoiceType;
  charge_mode?: ChargeMode;
  linked_project_id?: number | null;
  independently_visible?: boolean;
  coupon_eligible?: boolean;
  annual_gift_eligible?: boolean;
  qualifies_for_foot_bath_bundle?: boolean;
  status?: 'active' | 'inactive';
  display_order?: number;
  prices?: Array<{ price_type: PriceType; amount_cents: number; effective_from?: string }>;
};

export type OptionGroupPayload = {
  code: string;
  name: string;
  description: string;
  selection_mode: 'single' | 'multiple';
  required: boolean;
  min_select: number;
  max_select: number;
  display_order: number;
};

export type OptionChoicePayload = Omit<Required<OptionChoiceForm>, 'prices' | 'linked_project_id' | 'choice_type' | 'charge_mode'> & {
  choice_type: ChoiceType;
  charge_mode: ChargeMode;
  linked_project_id: number | null;
  prices: Array<{ price_type: PriceType; amount_cents: number; effective_from?: string }>;
};

export type CatalogValidationError = { code?: string; path?: string; message?: string };

export type PreviewOptionGroup = Pick<OptionGroupForm, 'selection_mode' | 'required' | 'min_select' | 'max_select'> & {
  choices: Array<{ id: number; status?: 'active' | 'inactive' }>;
};

const CHOICE_ERROR_MESSAGES: Record<string, string> = {
  linked_project_unpublished: '引用项目未发布，不能作为可选小项',
  linked_project_catalog_unpublished: '引用项目缺少已发布目录',
  linked_project_store_price_required: '引用项目未配置门店价',
  option_group_required: '选项组存在必选约束',
  option_group_min_select: '选项组最少选择数量不合法',
  option_group_max_select: '选项组最多选择数量不合法',
  draft_not_found: '项目没有可发布的目录草稿',
};

function clean(value: unknown): string {
  return String(value ?? '').trim();
}

export function optionGroupPayload(form: OptionGroupForm): OptionGroupPayload {
  const selectionMode = form.selection_mode === 'multiple' ? 'multiple' : 'single';
  const maxDefault = selectionMode === 'single' ? 1 : 0;
  const max = Math.max(0, Number(form.max_select ?? maxDefault));
  const min = Math.min(max, Math.max(0, Number(form.min_select ?? 0)));
  return {
    code: clean(form.code), name: clean(form.name), description: clean(form.description),
    selection_mode: selectionMode, required: Boolean(form.required),
    min_select: min, max_select: max, display_order: Math.max(0, Number(form.display_order ?? 0)),
  };
}

export function optionChoicePayload(form: OptionChoiceForm): OptionChoicePayload {
  const choiceType = form.choice_type || 'preference';
  const linked = choiceType === 'linked_project' ? (form.linked_project_id ?? null) : null;
  const chargeMode = choiceType === 'preference'
    ? 'free'
    : choiceType === 'linked_project' ? 'inherit_linked_price' : (form.charge_mode || 'custom_price');
  const prices = chargeMode === 'custom_price'
    ? (form.prices || []).map((price) => ({ ...price, amount_cents: Math.max(0, Number(price.amount_cents || 0)) }))
    : [];
  return {
    code: clean(form.code), name: clean(form.name), description: clean(form.description),
    choice_type: choiceType, charge_mode: chargeMode, linked_project_id: linked,
    independently_visible: form.independently_visible !== false,
    coupon_eligible: Boolean(form.coupon_eligible), annual_gift_eligible: Boolean(form.annual_gift_eligible),
    qualifies_for_foot_bath_bundle: Boolean(form.qualifies_for_foot_bath_bundle),
    status: form.status || 'active', display_order: Math.max(0, Number(form.display_order ?? 0)), prices,
  };
}

export function optionChoiceFormValues(form: OptionChoiceForm): OptionChoiceForm {
  if (form.choice_type !== 'dedicated_charge') return { ...form };
  const byType = new Map((form.prices || []).map((price) => [price.price_type, price]));
  const prices = (['store', 'group', 'member'] as PriceType[]).map((priceType) =>
    byType.get(priceType) || { price_type: priceType, amount_cents: 0 },
  );
  return { ...form, prices };
}

function readablePath(path: string): string {
  const last = path.split('.').filter(Boolean).pop() || '';
  return last === 'cupping' ? '拔罐' : last === 'local-strength' ? '局部加强' : last || '目录';
}

export function catalogValidationMessage(error: CatalogValidationError): string {
  const message = error.message || CHOICE_ERROR_MESSAGES[error.code || ''] || '目录发布检查未通过';
  return error.path ? `${readablePath(error.path)}：${message}` : message;
}

export function catalogPublishState(errors: CatalogValidationError[]): { canPublish: boolean; messages: string[] } {
  const messages = errors.map(catalogValidationMessage);
  return { canPublish: errors.length === 0, messages };
}

/**
 * 为管理端价格预览构造一组合法的最小选择集。
 * 后端预览会校验单选、必选、最少/最多数量，因此不能把目录里的所有
 * choice（尤其是停用项）直接提交过去。
 */
export function previewChoiceIds(groups: PreviewOptionGroup[]): number[] {
  const ids: number[] = [];
  for (const group of groups) {
    const active = group.choices.filter((choice) => choice.status !== 'inactive');
    const minSelect = Math.max(0, Number(group.min_select ?? 0));
    const requiredMin = group.required ? Math.max(1, minSelect) : minSelect;
    const defaultMax = group.selection_mode === 'single' ? 1 : 0;
    const maxSelect = Math.max(0, Number(group.max_select ?? defaultMax));
    const count = Math.min(active.length, requiredMin, maxSelect);
    ids.push(...active.slice(0, count).map((choice) => choice.id));
  }
  return ids;
}

export function formatCents(value: unknown): string {
  return typeof value === 'number' && Number.isFinite(value)
    ? `¥${(value / 100).toFixed(2)}`
    : '-';
}

export function nextTuesdayIso(timeZone: string): string {
  const candidate = new Date();
  candidate.setUTCHours(12, 0, 0, 0);
  const weekday = new Intl.DateTimeFormat('en-US', { timeZone, weekday: 'short' });
  for (let offset = 0; offset <= 14; offset += 1) {
    if (weekday.format(candidate) === 'Tue') return candidate.toISOString();
    candidate.setUTCDate(candidate.getUTCDate() + 1);
  }
  return candidate.toISOString();
}

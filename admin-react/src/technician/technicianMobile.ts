export const TECHNICIAN_MOBILE_ROUTES = ['/technician/today', '/technician/history', '/technician/me'] as const;
export const TECHNICIAN_MOBILE_TAB_PATHS = ['/today', '/history', '/me'] as const;

export function technicianMobileHome(role?: string): '/member-verify' | '/today' {
  return role === 'manager' ? '/member-verify' : '/today';
}

export function technicianMobileTabs(role?: string): readonly string[] {
  return role === 'manager' ? [] : TECHNICIAN_MOBILE_TAB_PATHS;
}

export function technicianAccountStatusLabel(status: string | undefined | null): string {
  return ({ active: '已启用', disabled: '已停用', resigned: '已离职', pending: '待激活' } as Record<string, string>)[status || ''] || '未知';
}

export function technicianEmploymentStatusLabel(status: string | undefined | null): string {
  return ({ available: '空闲', busy: '服务中', off: '休息', resigned: '已离职', suspended: '暂停服务' } as Record<string, string>)[status || ''] || '未知';
}

export function technicianStatusLabel(status: string): string {
  return ({ available: '空闲', waiting_service: '待开始', in_service: '服务中', post_service_present: '已完成', conflict: '待核对' } as Record<string, string>)[status] || '处理中';
}

export function technicianProfileStatusLabel(status: string): string {
  return status === 'confirmed' ? '顾客已确认' : '本次观察';
}

export type TechnicianHistoryProfileSummary = {
  service_lines?: string[];
  focus_areas?: string[];
  avoid_areas?: string[];
  force_preference?: string | null;
  temperature_preference?: string | null;
  service_feedback?: string | null;
  next_visit_plan?: string | null;
  communication_preference?: string | null;
  service_adjustments?: string[];
  body_reconfirm_required?: boolean;
};

const HISTORY_SUMMARY_VALUES = {
  areas: ['肩颈', '腰臀', '腿部', '腹部', '足部', '整体放松'],
  force: ['轻柔', '适中', '偏强'], temperature: ['偏低', '适中', '偏高'],
  feedback: ['本次合适', '调整后更合适', '下次需调整'], nextVisit: ['延续本次', '到店再确认'],
  communication: ['希望安静', '愿意聊天', '希望先沟通'],
  adjustments: ['减轻力度', '加强力度', '放慢节奏', '调低温度', '调高温度', '重点照顾', '避开该处', '提前结束'],
} as const;

function safeSummaryArray(value: unknown, allowed: readonly string[]): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string' && allowed.includes(item)) : [];
}

function safeSummaryValue(value: unknown, allowed: readonly string[]): string {
  return typeof value === 'string' && allowed.includes(value) ? value : '';
}

export function technicianHistorySummaryLines(summary: TechnicianHistoryProfileSummary | Record<string, unknown> | null): string[] {
  if (!summary) return [];
  if (Array.isArray(summary.service_lines)) return summary.service_lines.filter((line): line is string => typeof line === 'string' && line.length <= 300).slice(0, 10);
  const focusAreas = safeSummaryArray(summary.focus_areas, HISTORY_SUMMARY_VALUES.areas);
  const avoidAreas = safeSummaryArray(summary.avoid_areas, HISTORY_SUMMARY_VALUES.areas);
  const force = safeSummaryValue(summary.force_preference, HISTORY_SUMMARY_VALUES.force);
  const temperature = safeSummaryValue(summary.temperature_preference, HISTORY_SUMMARY_VALUES.temperature);
  const feedback = safeSummaryValue(summary.service_feedback, HISTORY_SUMMARY_VALUES.feedback);
  const nextVisit = safeSummaryValue(summary.next_visit_plan, HISTORY_SUMMARY_VALUES.nextVisit);
  const communication = safeSummaryValue(summary.communication_preference, HISTORY_SUMMARY_VALUES.communication);
  const adjustments = safeSummaryArray(summary.service_adjustments, HISTORY_SUMMARY_VALUES.adjustments);
  const lines = [
    focusAreas.length ? `重点：${focusAreas.join('、')}` : '', avoidAreas.length ? `避开或谨慎：${avoidAreas.join('、')}` : '',
    force ? `力度：${force}` : '', temperature ? `温度：${temperature}` : '', communication ? `沟通：${communication}` : '', adjustments.length ? `本次调整：${adjustments.join('、')}` : '', feedback ? `反馈：${feedback}` : '', nextVisit ? `下次：${nextVisit}` : '',
    summary.body_reconfirm_required === true ? '身体情况：服务前再确认' : '',
  ];
  return lines.filter(Boolean);
}

export function technicianHistoryEmptyState(status: 'all' | 'confirmed' | 'pending', unassignedLegacyCount: number): 'none' | 'legacy' | 'filtered' {
  if (status !== 'all') return 'filtered';
  return unassignedLegacyCount > 0 ? 'legacy' : 'none';
}

export function technicianPositionTone(status: string): 'idle' | 'waiting' | 'serving' | 'finished' | 'conflict' {
  if (status === 'waiting_service') return 'waiting';
  if (status === 'in_service') return 'serving';
  if (status === 'post_service_present') return 'finished';
  if (status === 'conflict') return 'conflict';
  return 'idle';
}

export function technicianActions(status: string): string[] {
  if (status === 'waiting_service') return ['confirm'];
  if (status === 'in_service') return ['finish'];
  if (status === 'post_service_present') return ['profile'];
  return [];
}

export function technicianOrderItemLabel(item: { name?: unknown; code?: unknown; diy_preferences?: unknown } | undefined | null): string {
  const name = typeof item?.name === 'string' ? item.name.trim() : '';
  const isLocalCare = item?.code === 'hxy-jubu-30' || name === '局部调理';
  if (!isLocalCare) return name || '服务项目';

  const bodyParts = Array.isArray(item?.diy_preferences)
    ? [...new Set(item.diy_preferences.filter((preference): preference is string => typeof preference === 'string').map((preference) => preference.trim()).filter(Boolean))]
    : [];
  return bodyParts.length ? `局部：${bodyParts.join('、')}` : (name || '局部调理');
}

export function technicianPriceLabel(cents: number | null | undefined): string {
  if (typeof cents !== 'number' || !Number.isFinite(cents) || cents < 0) return '—';
  return cents % 100 === 0 ? `¥${cents / 100}` : `¥${(cents / 100).toFixed(2)}`;
}

export type TechnicianPricingLine = {
  line_index?: number;
  name?: string;
  quantity?: number;
  unit_store_price_cents?: number | null;
  unit_member_price_cents?: number | null;
  store_line_total_cents?: number | null;
  member_line_total_cents?: number | null;
  group_line_total_cents?: number | null;
  store_line_price_cents?: number | null;
  member_line_price_cents?: number | null;
};

export type TechnicianOrderPricing = {
  store_total_cents?: number | null;
  member_total_cents?: number | null;
  group_total_cents?: number | null;
  member_saving_cents?: number | null;
  applied_price_type?: 'store' | 'member' | 'group' | null;
  lines?: TechnicianPricingLine[];
};

export function technicianPricingLines(pricing: TechnicianOrderPricing | null | undefined): TechnicianPricingLine[] {
  return Array.isArray(pricing?.lines) ? pricing.lines : [];
}

export type TechnicianPriceMode = 'member' | 'store' | 'group' | 'unknown';

export type TechnicianPriceAmount = {
  amount_cents: number | null;
  pending_label: string | null;
};

const GROUP_PRICE_PENDING = '团购价待确认';

/** 本单实际计价口径；缺失或未知时返回 unknown，避免用会员价/门店价冒充。 */
export function technicianPriceMode(pricing: TechnicianOrderPricing | null | undefined): TechnicianPriceMode {
  const applied = pricing?.applied_price_type;
  return applied === 'member' || applied === 'store' || applied === 'group' ? applied : 'unknown';
}

export function technicianPriceModeLabel(mode: TechnicianPriceMode): string {
  if (mode === 'member') return '会员价';
  if (mode === 'store') return '门店价';
  if (mode === 'group') return '团购价';
  return '价格类型待确认';
}

/** 逐项金额只按本单口径取值，group 缺少团购金额时给出待确认文案而不是借用会员/门店金额。 */
export function technicianPriceLineValue(mode: TechnicianPriceMode, line: TechnicianPricingLine | null | undefined): TechnicianPriceAmount {
  if (mode === 'member') return { amount_cents: technicianCentsOrNull(line?.member_line_total_cents ?? line?.member_line_price_cents), pending_label: null };
  if (mode === 'store') return { amount_cents: technicianCentsOrNull(line?.store_line_total_cents ?? line?.store_line_price_cents), pending_label: null };
  if (mode === 'group') {
    const amount = technicianCentsOrNull(line?.group_line_total_cents);
    return { amount_cents: amount, pending_label: amount === null ? GROUP_PRICE_PENDING : null };
  }
  return { amount_cents: null, pending_label: null };
}

/** 合计只按本单口径取值，与逐项金额口径保持一致。 */
export function technicianPriceTotalValue(mode: TechnicianPriceMode, pricing: TechnicianOrderPricing | null | undefined): TechnicianPriceAmount {
  if (mode === 'member') return { amount_cents: technicianCentsOrNull(pricing?.member_total_cents), pending_label: null };
  if (mode === 'store') return { amount_cents: technicianCentsOrNull(pricing?.store_total_cents), pending_label: null };
  if (mode === 'group') {
    const amount = technicianCentsOrNull(pricing?.group_total_cents);
    return { amount_cents: amount, pending_label: amount === null ? GROUP_PRICE_PENDING : null };
  }
  return { amount_cents: null, pending_label: null };
}

/** 服务位卡片/未排座行的一行价格摘要；无 pricing 时返回空字符串。 */
export function technicianPricingSummary(pricing: TechnicianOrderPricing | null | undefined): string {
  if (!pricing) return '';
  const mode = technicianPriceMode(pricing);
  if (mode === 'unknown') return technicianPriceModeLabel(mode);
  const total = technicianPriceTotalValue(mode, pricing);
  if (total.pending_label) return total.pending_label;
  return `${technicianPriceModeLabel(mode)} ${technicianPriceLabel(total.amount_cents)}`;
}

export type TechnicianPricedItemRow = {
  key: string;
  name: string;
  quantity: number;
  amount_cents: number | null;
  pending_label: string | null;
};

function technicianPositiveQuantity(value: unknown): number {
  const quantity = typeof value === 'number' ? value : Number(value);
  return Number.isInteger(quantity) && quantity > 0 ? quantity : 1;
}

function technicianCentsOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? Math.trunc(value) : null;
}

/**
 * 技师“我的服务”（GET /technician/my-tasks）的价格行映射。
 * 有 pricing 时按 applied_price_type 只取本单口径的逐项金额（与 /tasks 一致），
 * 并按 line_index 对齐任务项目；没有价格快照时只返回项目名且金额为 null，绝不伪造 0。
 */
export function technicianPricedItemRows(
  items: any[] | null | undefined,
  pricing: TechnicianOrderPricing | null | undefined,
): TechnicianPricedItemRow[] {
  const sourceItems = Array.isArray(items) ? items : [];
  const lines = technicianPricingLines(pricing);
  const mode = technicianPriceMode(pricing);
  if (lines.length) {
    return lines.map((line, index) => {
      const lineIndex = typeof line.line_index === 'number' ? line.line_index : index;
      const original = sourceItems.find((item, itemIndex) => Number(item?.line_index ?? itemIndex) === Number(lineIndex)) || sourceItems[index];
      const name = typeof line.name === 'string' && line.name.trim() ? line.name.trim() : technicianOrderItemLabel(original);
      const price = technicianPriceLineValue(mode, line);
      return {
        key: `line-${lineIndex}-${index}`,
        name,
        quantity: technicianPositiveQuantity(line.quantity !== undefined ? line.quantity : original?.quantity),
        amount_cents: price.amount_cents,
        pending_label: price.pending_label,
      };
    });
  }
  return sourceItems.map((item, index) => ({
    key: `item-${index}`,
    name: technicianOrderItemLabel(item),
    quantity: technicianPositiveQuantity(item?.quantity),
    amount_cents: null,
    pending_label: null,
  }));
}

export function createTechnicianIdempotencyKey(action: string, occupancyId: number): string {
  const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `tech-${action}-${occupancyId}-${suffix}`;
}

export function createTechnicianActionRunner(
  keyFactory: (action: string, occupancyId: number) => string = createTechnicianIdempotencyKey,
) {
  const actions = new Map<string, { key: string; pending?: Promise<unknown> }>();
  const scope = (action: string, occupancyId: number) => `${action}:${occupancyId}`;

  return {
    isRunning(action: string, occupancyId: number): boolean {
      return Boolean(actions.get(scope(action, occupancyId))?.pending);
    },
    run<T>(
      action: string,
      occupancyId: number,
      request: (occupancyId: number, idempotencyKey: string) => Promise<T>,
    ): Promise<T> {
      const actionScope = scope(action, occupancyId);
      const current = actions.get(actionScope);
      if (current?.pending) return current.pending as Promise<T>;

      const key = current?.key || keyFactory(action, occupancyId);
      const pending = request(occupancyId, key).then(
        (result) => {
          actions.delete(actionScope);
          return result;
        },
        (error) => {
          actions.set(actionScope, { key });
          throw error;
        },
      );
      actions.set(actionScope, { key, pending });
      return pending;
    },
  };
}

export type TechnicianBoardGroup = {
  key: string;
  label: string;
  items: any[];
};

function technicianPositionNumber(task: any): number {
  const label = String(task?.room_name || task?.customer_label || task?.name || '');
  const match = label.match(/\d+/);
  return match ? Number(match[0]) : Number.POSITIVE_INFINITY;
}

function compareTechnicianPositions(left: any, right: any): number {
  const leftNumber = technicianPositionNumber(left);
  const rightNumber = technicianPositionNumber(right);
  if (leftNumber !== rightNumber) return leftNumber < rightNumber ? -1 : 1;
  const leftLabel = String(left?.room_name || left?.customer_label || left?.name || '');
  const rightLabel = String(right?.room_name || right?.customer_label || right?.name || '');
  return leftLabel.localeCompare(rightLabel, 'zh-CN', { numeric: true })
    || Number(left?.room_id || 0) - Number(right?.room_id || 0);
}

export function technicianBoardGroups(tasks: any[]): TechnicianBoardGroup[] {
  const definitions = [
    { key: 'sofa', label: '沙发' },
    { key: 'room', label: '房间' },
    { key: 'other', label: '其他服务位' },
  ];
  return definitions
    .map(({ key, label }) => ({
      key,
      label,
      items: tasks.filter((task) => key === 'room'
        ? ['room', 'bed'].includes(task.room_type)
        : (task.room_type || 'other') === key).sort(compareTechnicianPositions),
    }))
    .filter((group) => group.items.length > 0);
}

export const TECHNICIAN_MOBILE_ROUTES = ['/technician/today', '/technician/history', '/technician/me'] as const;
export const TECHNICIAN_MOBILE_TAB_PATHS = ['/today', '/history', '/me'] as const;

export function technicianAccountStatusLabel(status: string | undefined | null): string {
  return ({ active: '已启用', disabled: '已停用', resigned: '已离职', pending: '待激活' } as Record<string, string>)[status || ''] || '未知';
}

export function technicianEmploymentStatusLabel(status: string | undefined | null): string {
  return ({ available: '空闲', busy: '服务中', off: '休息', resigned: '已离职', suspended: '暂停服务' } as Record<string, string>)[status || ''] || '未知';
}

export function technicianStatusLabel(status: string): string {
  return ({ available: '空闲', waiting_service: '待确认', in_service: '服务中', post_service_present: '已完成', conflict: '待核对' } as Record<string, string>)[status] || '处理中';
}

export function technicianProfileStatusLabel(status: string): string {
  return status === 'confirmed' ? '顾客已确认' : '本次观察';
}

export type TechnicianHistoryProfileSummary = {
  focus_areas?: string[];
  avoid_areas?: string[];
  force_preference?: string | null;
  temperature_preference?: string | null;
  service_feedback?: string | null;
  next_visit_plan?: string | null;
  occupation_contexts?: string[];
  relaxation?: string | null;
  decision_priorities?: string[];
  budget_preference?: string | null;
};

const HISTORY_SUMMARY_VALUES = {
  areas: ['肩颈', '腰臀', '腿部', '腹部', '足部', '整体放松'],
  force: ['轻柔', '适中', '偏强'], temperature: ['偏低', '适中', '偏高'],
  feedback: ['本次合适', '调整后更合适', '下次需调整'], nextVisit: ['延续本次', '到店再确认'],
  occupations: ['久坐办公', '久站服务', '经常驾驶', '体力劳动', '照护家庭', '自由职业', '退休', '其他'],
  relaxation: ['较快', '逐渐', '始终较紧张'], decisions: ['价格', '品质', '环境', '效率', '固定技师', '固定时段'],
  budget: ['实惠优先', '平衡', '体验优先', '未表达'],
} as const;

function safeSummaryArray(value: unknown, allowed: readonly string[]): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string' && allowed.includes(item)) : [];
}

function safeSummaryValue(value: unknown, allowed: readonly string[]): string {
  return typeof value === 'string' && allowed.includes(value) ? value : '';
}

export function technicianHistorySummaryLines(summary: TechnicianHistoryProfileSummary | Record<string, unknown> | null): string[] {
  if (!summary) return [];
  const focusAreas = safeSummaryArray(summary.focus_areas, HISTORY_SUMMARY_VALUES.areas);
  const avoidAreas = safeSummaryArray(summary.avoid_areas, HISTORY_SUMMARY_VALUES.areas);
  const force = safeSummaryValue(summary.force_preference, HISTORY_SUMMARY_VALUES.force);
  const temperature = safeSummaryValue(summary.temperature_preference, HISTORY_SUMMARY_VALUES.temperature);
  const feedback = safeSummaryValue(summary.service_feedback, HISTORY_SUMMARY_VALUES.feedback);
  const nextVisit = safeSummaryValue(summary.next_visit_plan, HISTORY_SUMMARY_VALUES.nextVisit);
  const occupations = safeSummaryArray(summary.occupation_contexts, HISTORY_SUMMARY_VALUES.occupations);
  const relaxation = safeSummaryValue(summary.relaxation, HISTORY_SUMMARY_VALUES.relaxation);
  const decisions = safeSummaryArray(summary.decision_priorities, HISTORY_SUMMARY_VALUES.decisions);
  const budget = safeSummaryValue(summary.budget_preference, HISTORY_SUMMARY_VALUES.budget);
  const lines = [
    focusAreas.length ? `重点：${focusAreas.join('、')}` : '', avoidAreas.length ? `避开或谨慎：${avoidAreas.join('、')}` : '',
    force ? `力度：${force}` : '', temperature ? `温度：${temperature}` : '', feedback ? `反馈：${feedback}` : '', nextVisit ? `下次：${nextVisit}` : '',
    occupations.length ? `职业场景：${occupations.join('、')}` : '', relaxation ? `放松过程：${relaxation}` : '',
    decisions.length ? `决策关注：${decisions.join('、')}` : '', budget ? `预算倾向：${budget}` : '',
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

export function createTechnicianIdempotencyKey(action: string, occupancyId: number): string {
  const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `tech-${action}-${occupancyId}-${suffix}`;
}

export type TechnicianBoardGroup = {
  key: string;
  label: string;
  items: any[];
};

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
        : (task.room_type || 'other') === key),
    }))
    .filter((group) => group.items.length > 0);
}

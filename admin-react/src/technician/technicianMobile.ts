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

export function technicianHistorySummaryLines(summary: TechnicianHistoryProfileSummary | null): string[] {
  if (!summary) return [];
  const lines = [
    summary.focus_areas?.length ? `重点：${summary.focus_areas.join('、')}` : '',
    summary.avoid_areas?.length ? `避开或谨慎：${summary.avoid_areas.join('、')}` : '',
    summary.force_preference ? `力度：${summary.force_preference}` : '',
    summary.temperature_preference ? `温度：${summary.temperature_preference}` : '',
    summary.service_feedback ? `反馈：${summary.service_feedback}` : '',
    summary.next_visit_plan ? `下次：${summary.next_visit_plan}` : '',
    summary.occupation_contexts?.length ? `职业场景：${summary.occupation_contexts.join('、')}` : '',
    summary.relaxation ? `放松过程：${summary.relaxation}` : '',
    summary.decision_priorities?.length ? `决策关注：${summary.decision_priorities.join('、')}` : '',
    summary.budget_preference ? `预算倾向：${summary.budget_preference}` : '',
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

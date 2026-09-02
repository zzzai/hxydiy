export const TECHNICIAN_MOBILE_ROUTES = ['/technician/today', '/technician/history', '/technician/me'] as const;

/** Staff 登录账号状态（与 Technician 服务状态分开呈现）。 */
export function technicianAccountStatusLabel(status: string | undefined | null): string {
  return ({ active: '已启用', disabled: '已停用', resigned: '已离职', pending: '待激活' } as Record<string, string>)[status || ''] || '未知';
}

/** Technician 当前服务资格状态。 */
export function technicianEmploymentStatusLabel(status: string | undefined | null): string {
  return ({ available: '空闲', busy: '服务中', off: '休息', resigned: '已离职', suspended: '暂停服务' } as Record<string, string>)[status || ''] || '未知';
}

export function technicianStatusLabel(status: string): string {
  return ({ available: '空闲', waiting_service: '待确认', in_service: '服务中', post_service_present: '已完成', conflict: '待核对' } as Record<string, string>)[status] || '处理中';
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

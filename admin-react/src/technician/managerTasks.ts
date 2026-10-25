export type UnresolvedTask = {
  id: number;
  status: 'open' | 'acknowledged';
  label: string;
  assigned_to: string | null;
  due_at: string | null;
  overdue: boolean;
};

const labels: Record<string, string> = {
  missing_selection: '服务订单缺选单',
  missing_order: '选单缺履约订单',
  amount_mismatch: '选单与订单金额需要核对',
  status_mismatch: '服务进度需要核对',
  service_missing_selection: '服务位关联选单缺失',
  service_inactive_selection: '服务位关联选单已取消或过期',
  service_store_mismatch: '服务位与选单跨店',
  service_room_store_mismatch: '服务位房间跨店',
};

export function readUnresolvedTasks(payload: unknown): UnresolvedTask[] {
  if (!payload || typeof payload !== 'object' || !('items' in payload) || !Array.isArray(payload.items)) {
    throw new Error('Invalid task response');
  }
  const seen = new Set<number>();
  const result: UnresolvedTask[] = [];
  for (const item of payload.items) {
    if (!item || !Number.isSafeInteger(item.id) || item.id <= 0 || !['open', 'acknowledged', 'resolved'].includes(item.status)) {
      throw new Error('Invalid task item');
    }
    if (item.status === 'resolved' || seen.has(item.id)) continue;
    seen.add(item.id);
    result.push({
      id: item.id, status: item.status,
      label: labels[item.exception_type] || '服务信息需要核对',
      assigned_to: typeof item.assigned_to === 'string' ? item.assigned_to : null,
      due_at: typeof item.due_at === 'string' ? item.due_at : null,
      overdue: item.overdue === true,
    });
  }
  return result;
}

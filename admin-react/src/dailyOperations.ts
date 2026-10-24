export const EXCEPTION_LABELS: Record<string, string> = {
  missing_selection: '服务单缺少选单', missing_order: '选单缺少履约单',
  status_mismatch: '服务进度需要核对', amount_mismatch: '选单与服务单金额需要核对',
};
export function exceptionLabel(type: string): string { return EXCEPTION_LABELS[type] || '服务信息需要核对'; }
export function exceptionStatus(status: string): string {
  return ({ open: '待核对', acknowledged: '已知悉 · 待处理', resolved: '已记录处理结果' } as Record<string, string>)[status] || '状态待核实';
}
export function attentionDestination(key: string): string | null {
  return ({ low_review: '/feedback', exception_queue: '/exceptions', exception_overdue: '/exceptions', stale_order: '/selection-sessions', unassigned_service: '/service-positions' } as Record<string, string>)[key] || null;
}
export function serviceStatus(status: string): string {
  return ({ submitted: '待确认', confirmed: '已确认', waiting: '待安排', waiting_service: '待服务', arrived: '已到店', checked_in: '已到店', assigned: '已安排技师', in_service: '服务中', completed: '已完成', finished: '已完成', pending_checkout: '服务已结束', post_service_present: '服务已结束', cancelled: '已取消' } as Record<string, string>)[status] || '进度待核实';
}
export function selectionSource(source: string): string {
  return ({ tablet: '门店平板', mini_program: '顾客手机', personal_qr: '顾客扫码', in_store: '到店选购', wecom: '企微入口' } as Record<string, string>)[source] || '门店入口';
}
export function displayCount(value: unknown): number | '—' {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? value : '—';
}
export type OperationalException = {
  id: number; exception_type: string; status: 'open' | 'acknowledged' | 'resolved';
  entity_type: string; entity_id: string; assigned_to: string | null; due_at: string | null;
  overdue: boolean; created_at: string | null; acknowledged_at?: string | null;
  resolved_at?: string | null; resolution_note?: string | null;
};
export function readExceptions(payload: unknown): OperationalException[] {
  if (!payload || typeof payload !== 'object' || !('items' in payload) || !Array.isArray(payload.items)) throw new Error('Invalid exception response');
  if (payload.items.some(item => !item || !Number.isSafeInteger(item.id) || item.id <= 0 || !['open', 'acknowledged', 'resolved'].includes(item.status))) throw new Error('Invalid exception item');
  return payload.items;
}
export function operationTime(value?: string | null): string {
  if (!value || Number.isNaN(Date.parse(value))) return '未记录';
  return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
}

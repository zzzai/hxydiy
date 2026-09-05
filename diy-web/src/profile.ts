/** 个人中心展示工具：脱敏、状态文案、时间格式化。 */

export const ANNUAL_MEMBERSHIP_BENEFITS = {
  standard: '全年消费享会员价',
  tuesday: '每周二，会员价与门店价 6.8 折取较低价',
  gift: '办理会员年度权益卡时，可获赠 1 项门店价 99 元以下项目；仅赠送一次，不与其他优惠叠加',
} as const;

export function maskedPhone(phone: string): string {
  if (phone.length !== 11) return phone;
  return `${phone.slice(0, 3)}****${phone.slice(7)}`;
}

const ORDER_STATUS_LABELS: Record<string, string> = {
  draft: '待前台确认',
  pending_payment: '待前台确认',
  paid: '已由门店确认',
  confirmed: '已由门店确认',
  checked_in: '已由门店确认',
  in_service: '服务中',
  pending_checkout: '待结算',
  pending_feedback: '待评价',
  completed: '已完成',
  expired: '已过期',
  cancelled: '已取消',
  cancellation_requested: '退款申请中',
  refund_pending: '退款处理中',
  refunded: '已退款',
  refund_rejected: '退款未通过',
  partially_refunded: '部分退款',
};

export function orderStatusLabel(status: string): string {
  return ORDER_STATUS_LABELS[status] || status;
}

/** 兼容旧订单状态：仅尚未由门店确认的记录支持顾客自助取消。 */
export function canSelfCancelOrder(status: string): boolean {
  return status === 'pending_payment';
}

const SELECTION_STATUS_LABELS: Record<string, string> = {
  draft: '选购中',
  submitted: '待前台确认',
  confirmed: '已由门店确认',
  cancelled: '已取消',
  expired: '已过期',
};

export function selectionStatusLabel(status: string): string {
  return SELECTION_STATUS_LABELS[status] || status;
}

export function selectionDisplayAmount(session: {
  pricing_snapshot?: Record<string, unknown> | null;
  store_total_cents?: number | null;
  group_total_cents?: number | null;
  member_total_cents?: number | null;
}): number {
  const snapshot = session.pricing_snapshot || {};
  const payable = snapshot.payable_total_cents;
  if (typeof payable === 'number' && Number.isFinite(payable)) return Math.max(0, payable);
  const applied = snapshot.applied_price_type;
  if (applied === 'member' && typeof session.member_total_cents === 'number') return Math.max(0, session.member_total_cents);
  if (applied === 'group' && typeof session.group_total_cents === 'number') return Math.max(0, session.group_total_cents);
  return Math.max(0, session.store_total_cents || 0);
}

export function membershipSavingCents(sessions: Array<{
  service_completed_at?: string | null;
  store_total_cents?: number | null;
  member_total_cents?: number | null;
}>): number {
  return sessions.reduce((total, session) => {
    if (!session.service_completed_at) return total;
    const store = Number(session.store_total_cents || 0);
    const member = Number(session.member_total_cents || 0);
    return total + (Number.isFinite(store) && Number.isFinite(member) ? Math.max(0, store - member) : 0);
  }, 0);
}

export function membershipState(expireAt: string | null | undefined, now = new Date()): { kind: 'active' | 'expiring' | 'expired' | 'unknown'; daysLeft: number | null } {
  if (!expireAt) return { kind: 'unknown', daysLeft: null };
  const expires = new Date(expireAt);
  if (Number.isNaN(expires.getTime())) return { kind: 'unknown', daysLeft: null };
  const daysLeft = Math.max(0, Math.ceil((expires.getTime() - now.getTime()) / 86_400_000));
  if (expires.getTime() <= now.getTime()) return { kind: 'expired', daysLeft: 0 };
  return { kind: daysLeft <= 30 ? 'expiring' : 'active', daysLeft };
}

export type RecordFilter = 'all' | 'pending-feedback' | 'in-service' | 'completed';
export function recordFilter<T extends { can_evaluate?: boolean; evaluated?: boolean; occupancy_status?: string | null }>(records: T[], filter: RecordFilter): T[] {
  if (filter === 'pending-feedback') return records.filter((item) => item.can_evaluate && !item.evaluated);
  if (filter === 'in-service') return records.filter((item) => item.occupancy_status === 'waiting_service' || item.occupancy_status === 'in_service');
  if (filter === 'completed') return records.filter((item) => item.can_evaluate || ['post_service_present', 'cleaning', 'released'].includes(item.occupancy_status || ''));
  return records;
}

const COUPON_STATUS_LABELS: Record<string, string> = {
  unused: '未使用',
  used: '已使用',
  expired: '已过期',
  locked: '已锁定',
};

export function couponStatusLabel(status: string): string {
  return COUPON_STATUS_LABELS[status] || status;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

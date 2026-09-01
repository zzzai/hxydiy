export type OperationAction = 'ready' | 'finish';

export interface NextOperation {
  action: OperationAction;
  label: string;
}

export interface LiveVisit {
  id: number;
  status: string;
  arrived_at: string | null;
  order_id: number;
  order_no: string;
  user_id: number;
  items: Array<{ name?: string; quantity?: number }>;
  pay_amount_cents: number;
  service_order_id: number;
  service_order_status: string;
  assignment_id: number | null;
  assignment_status: string | null;
  technician_id: number | null;
  technician_name: string;
  room_id: number | null;
  room_name: string;
}

export interface LiveResource {
  id: number;
  name: string;
  status: string;
  can_finish_cleaning?: boolean;
}

export interface LiveBoard {
  summary: Record<string, number>;
  visits: LiveVisit[];
  resources: {
    technicians: LiveResource[];
    rooms: LiveResource[];
  };
}

const RESOURCE_STATUS: Record<string, { color: string; text: string }> = {
  available: { color: 'green', text: '可用' },
  reserved: { color: 'blue', text: '已预留' },
  occupied: { color: 'cyan', text: '已入座' },
  in_service: { color: 'purple', text: '服务中' },
  pending_checkout: { color: 'orange', text: '待结账' },
  cleaning: { color: 'gold', text: '待清洁' },
  busy: { color: 'purple', text: '忙碌' },
  inspection: { color: 'gold', text: '检查中' },
  maintenance: { color: 'red', text: '维护中' },
  off: { color: 'default', text: '休息' },
  resting: { color: 'default', text: '休息中' },
  resigned: { color: 'default', text: '离职' },
};

export function getResourceStatus(status: string) {
  return RESOURCE_STATUS[status] || { color: 'default', text: status };
}

export function canFinishRoomCleaning(resource: LiveResource): boolean {
  return resource.status === 'cleaning' && resource.can_finish_cleaning === true;
}

export function getOperationConfirmation(label: string): string {
  return `${label}？`;
}

export function getNextOperation(
  visitStatus: string,
  serviceOrderStatus: string,
): NextOperation | null {
  // DIY 管理端不负责派钟；等待现场分配时不提供操作。
  if (visitStatus === 'assigned' && serviceOrderStatus === 'assigned') {
    return { action: 'ready', label: '确认服务' };
  }
  if (visitStatus === 'in_service' && serviceOrderStatus === 'in_service') {
    return { action: 'finish', label: '服务结束' };
  }
  return null;
}

export function makeIdempotencyKey(action: string, entityId: number | string): string {
  const safeAction = action.replace(/[^a-z0-9-]/gi, '').slice(0, 16) || 'operation';
  return `${safeAction}-${entityId}-${crypto.randomUUID()}`.slice(0, 64);
}

export function buildSelectionSettlementPayload(
  payableTotalCents: number,
  paymentMethod: string,
  reason = '',
) {
  return {
    payment_method: paymentMethod,
    received_amount_cents: Math.max(0, Math.round(payableTotalCents)),
    payment_reference: '',
    reason,
  };
}

export function buildAbnormalSelectionSettlementPayload(input: {
  originalPayableCents: number;
  adjustmentCents: number;
  paymentMethod: string;
  reasonCode: string;
  responsibility: string;
  reason: string;
}) {
  const original = Math.max(0, Math.round(input.originalPayableCents));
  const adjustment = Math.min(original, Math.max(0, Math.round(input.adjustmentCents)));
  return {
    payment_method: input.paymentMethod,
    received_amount_cents: original - adjustment,
    payment_reference: '',
    service_adjustment_cents: adjustment,
    adjustment_reason_code: input.reasonCode,
    responsibility: input.responsibility,
    reason: input.reason,
  };
}

export function buildRefundNotePayload(input: {
  amountCents: number;
  reasonCode: string;
  responsibility: string;
  refundReference: string;
  reason: string;
}) {
  return {
    amount_cents: Math.max(0, Math.round(input.amountCents)),
    reason_code: input.reasonCode,
    responsibility: input.responsibility,
    refund_reference: input.refundReference,
    reason: input.reason,
  };
}

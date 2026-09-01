export type OccupancyStatus =
  | 'available'
  | 'held'
  | 'waiting_service'
  | 'in_service'
  | 'post_service_present'
  | 'cleaning'
  | 'released'
  | 'unavailable';

export type PositionAction =
  | 'start_service'
  | 'finish_service'
  | 'settle_selection'
  | 'retain'
  | 'move'
  | 'force_release';

export type PositionRole = 'admin' | 'staff' | string | undefined;

export type PositionOccupancy = {
  id: number;
  store_id: number;
  room_id: number;
  selection_session_id: string;
  active_room_id: number | null;
  status: Exclude<OccupancyStatus, 'available' | 'unavailable'>;
  source: string;
  hold_expires_at: string | null;
  retained_until: string | null;
  expected_end_at: string | null;
  actual_start_at: string | null;
  actual_service_end_at: string | null;
  departed_at: string | null;
  released_at: string | null;
  release_reason: string;
  version: number;
};

export type SelectionSummary = {
  id: string;
  status: string;
  fulfillment_order_id: number | null;
  service_order_status: string | null;
  source: string;
  device_label: string;
  items: Array<{
    project_id: number | string;
    name?: string;
    quantity?: number;
    diy_preferences?: string[];
    item_type?: string;
  }>;
  pricing_snapshot: Record<string, unknown>;
  store_total_cents: number;
  member_total_cents: number;
  submitted_at: string | null;
};

export type ServicePosition = {
  id: number;
  code: string;
  name: string;
  customer_label: string;
  type: 'sofa' | 'room' | 'bed';
  state: OccupancyStatus;
  is_current: boolean;
  customer_selectable: boolean;
  operational_status: string;
  map_x: number;
  map_y: number;
  map_width: number;
  map_height: number;
  sort_order: number;
  occupancy: PositionOccupancy | null;
  selection: SelectionSummary | null;
};

export const DEFAULT_SERVICE_POSITION_LAYOUT = [
  ...Array.from({ length: 8 }, (_, index) => ({ type: 'sofa' as const, code: `sofa-${String(index + 1).padStart(2, '0')}`, name: `${index + 1}号沙发` })),
  ...Array.from({ length: 9 }, (_, index) => ({ type: 'bed' as const, code: `bed-${String(index + 1).padStart(2, '0')}`, name: `${index + 1}号房间床位` })),
] as const;

export function normalizeServicePositions(positions: ServicePosition[]): ServicePosition[] {
  const canonical = new Map(DEFAULT_SERVICE_POSITION_LAYOUT.map((item) => [item.code, item]));
  const valid = new Map<string, ServicePosition>();
  positions.forEach((position) => {
    const expected = canonical.get(position.code);
    if (expected && expected.type === position.type && !valid.has(position.code)) valid.set(position.code, position);
  });
  return DEFAULT_SERVICE_POSITION_LAYOUT.map((item, index) => valid.get(item.code) || {
      id: -(index + 1), code: item.code, name: item.name, customer_label: item.name,
      type: item.type, state: 'unavailable' as const, is_current: false, customer_selectable: false,
      operational_status: 'inactive', map_x: 0, map_y: 0, map_width: 1, map_height: 1,
      sort_order: 1000 + index, occupancy: null, selection: null,
    });
}

export function splitPositionGroups(positions: ServicePosition[]) {
  return {
    sofas: positions.filter((position) => position.type === 'sofa'),
    rooms: positions.filter((position) => position.type !== 'sofa'),
  };
}

export function positionTypeLabel(type: ServicePosition['type']): string {
  if (type === 'sofa') return '大厅沙发';
  if (type === 'bed') return '房间床位';
  return '独立房间';
}

export type LiveServicePositionMap = {
  store_id: number;
  positions: ServicePosition[];
  updated_at: string;
};

export type OccupancyStatusMeta = {
  label: string;
  color: string;
  tone: 'available' | 'pending' | 'active' | 'attention' | 'cleaning' | 'muted';
  description: string;
};

export type WaitingReleaseMeta = {
  level: 'normal' | 'warning' | 'urgent' | 'overdue' | 'confirmed';
  label: string;
  dueAt: string | null;
  remainingMs: number | null;
};

export type ReleaseCandidate = {
  occupancy_id: number;
  version: number;
  room_id: number;
  room_code: string;
  status: 'held' | 'waiting_service';
  selection_session_id: string;
  due_at: string;
  overdue_seconds: number;
  reason_code: 'hold_expired' | 'waiting_service_expired';
};

export type BulkReleaseResult = {
  released: number[];
  skipped: Array<{ occupancy_id: number; reason: string }>;
};

const STATUS_META: Record<OccupancyStatus, OccupancyStatusMeta> = {
  available: { label: '可用', color: '#2f8b69', tone: 'available', description: '可接待新顾客' },
  held: { label: '临时占用', color: '#c78b2d', tone: 'pending', description: '顾客正在选择项目' },
  waiting_service: { label: '待服务', color: '#3178c6', tone: 'pending', description: '选单已提交，等待开始' },
  in_service: { label: '服务中', color: '#1f6f5b', tone: 'active', description: '顾客正在接受服务' },
  post_service_present: { label: '服务完成·仍在位', color: '#ad5b34', tone: 'attention', description: '服务已结束，顾客尚未离位' },
  cleaning: { label: '待清洁', color: '#7256a8', tone: 'cleaning', description: '顾客已离位，完成清洁后释放' },
  released: { label: '已释放', color: '#84928e', tone: 'muted', description: '本次占用已结束' },
  unavailable: { label: '暂不可用', color: '#84928e', tone: 'muted', description: '维修或停用中' },
};

const STAFF_ACTIONS: Partial<Record<OccupancyStatus, PositionAction[]>> = {
  held: [],
  waiting_service: ['start_service'],
  in_service: ['finish_service'],
  post_service_present: [],
  cleaning: [],
};

export function occupancyStatusMeta(status: OccupancyStatus | string): OccupancyStatusMeta {
  return STATUS_META[status as OccupancyStatus] ?? {
    label: status || '未知',
    color: '#84928e',
    tone: 'muted',
    description: '状态信息待刷新',
  };
}

export function getPositionActions(
  status: OccupancyStatus | string,
  role: PositionRole,
  hasFulfillmentOrder = false,
  fulfillmentServiceOrderStatus?: string | null,
  abnormalService = false,
  selectionStatus?: string | null,
): PositionAction[] {
  if (role !== 'admin' && role !== 'manager') return [];
  const actions = [...(STAFF_ACTIONS[status as OccupancyStatus] ?? [])]
    .filter((action) => (
      !hasFulfillmentOrder
      || action === 'force_release'
      || fulfillmentServiceOrderStatus === 'completed'
    ));
  void role; void abnormalService; void selectionStatus;
  return actions;
}

export function getForceReleaseTargets(status: OccupancyStatus | string): Array<'released' | 'cleaning'> {
  if (status === 'waiting_service') return ['released', 'cleaning'];
  if (status === 'in_service' || status === 'post_service_present') return ['cleaning'];
  return ['released'];
}

export function getServicePositionOperationalAction(
  operationalStatus: string,
  hasActiveOccupancy: boolean,
): 'enable' | 'disable' | null {
  if (hasActiveOccupancy) return null;
  if (operationalStatus === 'active') return 'disable';
  if (operationalStatus === 'inactive') return 'enable';
  return null;
}

export const POSITION_ACTION_LABELS: Record<PositionAction, string> = {
  start_service: '确认服务',
  finish_service: '服务结束',
  settle_selection: '服务结算',
  retain: '继续保留 30 分钟',
  move: '调整服务位',
  force_release: '强制释放',
};

export function waitingReleaseMeta(
  occupancy: PositionOccupancy,
  selectionStatus: string | null | undefined,
  submittedAt: string | null | undefined,
  now: number,
): WaitingReleaseMeta {
  if (selectionStatus === 'confirmed') {
    return {
      level: 'confirmed',
      label: '前台已确认，等待开始服务',
      dueAt: null,
      remainingMs: null,
    };
  }
  const submittedMs = submittedAt ? Date.parse(submittedAt) : Number.NaN;
  const retainedMs = occupancy.retained_until ? Date.parse(occupancy.retained_until) : Number.NaN;
  const defaultDueMs = Number.isFinite(submittedMs) ? submittedMs + 60 * 60_000 : Number.NaN;
  const dueMs = Number.isFinite(retainedMs)
    ? Math.max(retainedMs, defaultDueMs)
    : defaultDueMs;
  if (occupancy.status !== 'waiting_service' || !Number.isFinite(dueMs)) {
    return { level: 'normal', label: '等待前台处理', dueAt: null, remainingMs: null };
  }
  const remainingMs = dueMs - now;
  if (remainingMs <= 0) {
    return { level: 'overdue', label: '等待已超时，可核对后释放', dueAt: new Date(dueMs).toISOString(), remainingMs };
  }
  if (remainingMs <= 10 * 60_000) {
    return { level: 'urgent', label: '即将释放，请确认顾客是否仍在等候', dueAt: new Date(dueMs).toISOString(), remainingMs };
  }
  if (remainingMs <= 30 * 60_000) {
    return { level: 'warning', label: '等待较久，请留意现场情况', dueAt: new Date(dueMs).toISOString(), remainingMs };
  }
  return { level: 'normal', label: '等待开始服务', dueAt: new Date(dueMs).toISOString(), remainingMs };
}

export function countPositionStates(positions: Array<Pick<ServicePosition, 'state'>>) {
  return positions.reduce((counts, position) => {
    if (position.state === 'available') counts.available += 1;
    else if (position.state === 'held') counts.held += 1;
    else if (position.state === 'waiting_service') counts.waiting_service += 1;
    else if (position.state === 'in_service') counts.in_service += 1;
    else if (position.state === 'post_service_present' || position.state === 'cleaning') counts.attention += 1;
    else if (position.state === 'unavailable') counts.unavailable += 1;
    return counts;
  }, { available: 0, held: 0, waiting_service: 0, in_service: 0, attention: 0, unavailable: 0 });
}

export function buildKioskUrl(
  baseUrl: string,
  storeId: number,
  sessionId: string,
  accessToken: string,
): string {
  const url = new URL(baseUrl);
  url.searchParams.set('store', String(storeId));
  url.searchParams.set('session', sessionId);
  url.searchParams.set('token', accessToken);
  url.searchParams.set('source', 'kiosk');
  return url.toString();
}

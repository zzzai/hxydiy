import type { Occupancy, ServicePosition } from './api';

export type PositionSelectionContext = {
  mode: 'entry' | 'move';
  source?: string;
  currentType?: ServicePosition['type'];
  occupancyStatus?: Occupancy['status'];
  moving?: boolean;
};

export type PositionSelectionDecision = {
  selectable: boolean;
  label: string;
  reason: string;
};

const OCCUPIED_POSITION_COPY: Partial<Record<ServicePosition['state'], Omit<PositionSelectionDecision, 'selectable'>>> = {
  held: { label: '已临时占用', reason: '该沙发正在为其他顾客临时保留' },
  waiting_service: { label: '待服务', reason: '该沙发已有顾客等待服务' },
  in_service: { label: '服务中', reason: '该沙发正在服务中' },
  post_service_present: { label: '服务已结束', reason: '顾客尚未离开该沙发' },
  cleaning: { label: '清洁中', reason: '该沙发清洁完成后才可使用' },
  unavailable: { label: '暂停使用', reason: '该沙发当前暂停使用，请选择其他位置' },
};

function moveLockDecision(context: PositionSelectionContext): PositionSelectionDecision | null {
  if (context.currentType === 'room') {
    return { selectable: false, label: '需前台换位', reason: '房间由二维码绑定，如需换位请联系前台' };
  }
  if (context.source === 'kiosk') {
    return { selectable: false, label: '需前台换位', reason: '共享设备由前台绑定服务位，如需换位请联系前台' };
  }
  switch (context.occupancyStatus) {
    case 'held':
      return null;
    case 'waiting_service':
      return { selectable: false, label: '需前台换位', reason: '已提交前台，如需换位请联系前台' };
    case 'in_service':
      return { selectable: false, label: '需前台换位', reason: '服务已经开始，如需换位请联系前台' };
    case 'post_service_present':
      return { selectable: false, label: '需前台换位', reason: '本次服务已结束，如需调整位置请联系前台' };
    case 'cleaning':
      return { selectable: false, label: '需前台换位', reason: '当前服务位正在清洁，请联系前台安排' };
    case 'released':
    default:
      return { selectable: false, label: '请刷新', reason: '当前服务位状态已变化，请刷新后重试' };
  }
}

export type EntrySourceInput = {
  source?: string;
  qrToken?: string;
  positionCode: string;
};

export function getEntrySource(input: EntrySourceInput): string {
  if (input.source) return input.source;
  if (!input.qrToken) return 'store_qr';
  return input.positionCode.startsWith('room-') ? 'room_qr' : 'personal_qr';
}

/**
 * URL/已绑定编码是顾客入口的服务位事实来源；只有没有请求编码时，
 * 才允许使用服务端标记的当前位作为回退，避免旧会话把二维码串到另一张沙发。
 */
export function resolveRequestedPosition(
  positions: ServicePosition[],
  requestedCode?: string,
): ServicePosition | undefined {
  const code = String(requestedCode || '').trim();
  if (code) return positions.find((item) => item.code === code);
  return positions.find((item) => item.is_current);
}

/**
 * After a customer explicitly changes seats, the in-memory active code is the
 * current truth. The URL code is only the initial entry hint and can be stale
 * because history.replaceState does not update the boot-time query snapshot.
 */
export function resolveActivePositionCode(activeCode?: string, initialCode?: string): string {
  return String(activeCode || '').trim() || String(initialCode || '').trim();
}

export function getPositionSelectionDecision(
  position: ServicePosition,
  context: PositionSelectionContext,
): PositionSelectionDecision {
  if (position.is_current) {
    return { selectable: false, label: '当前位置', reason: '这里就是您当前绑定的服务位' };
  }
  if (context.moving) {
    return { selectable: false, label: '正在切换', reason: '正在切换服务位，请稍候' };
  }
  if (!position.customer_selectable || position.operational_status !== 'active') {
    return { selectable: false, label: '暂停使用', reason: '该沙发当前暂停使用，请选择其他位置' };
  }
  const occupiedCopy = OCCUPIED_POSITION_COPY[position.state];
  if (occupiedCopy) {
    return { selectable: false, ...occupiedCopy };
  }
  if (context.mode === 'entry') {
    return { selectable: true, label: '可选择', reason: `点击进入 ${position.customer_label}` };
  }
  const lock = moveLockDecision(context);
  if (lock) return lock;
  return { selectable: true, label: '可换到这里', reason: `点击切换到 ${position.customer_label}` };
}

export function resolveEntryConflict(code: string, currentPositionCode?: string, status?: number):
  | { action: 'refresh-map' }
  | { action: 'resume-current'; positionCode: string }
  | { action: 'show-error' } {
  if (code === 'POSITION_OCCUPIED' || code === 'POSITION_UNAVAILABLE' || status === 404) {
    return { action: 'refresh-map' };
  }
  if (code === 'BROWSER_ACTIVE_ELSEWHERE' && currentPositionCode) {
    return { action: 'resume-current', positionCode: currentPositionCode };
  }
  return { action: 'show-error' };
}

export function shouldResumeCurrentPosition(input: {
  requestedCode?: string;
  qrToken?: string;
  conflict: ReturnType<typeof resolveEntryConflict>;
}): boolean {
  return input.conflict.action === 'resume-current'
    && !String(input.requestedCode || '').trim()
    && !input.qrToken;
}

import { managerPrice, managerSourceLabel, managerStatusLabel } from './managerMobile.ts';
import type { ManagerSelectionItem } from './managerMobile.ts';

export type ManagerPositionDetail = {
  positionId: number; occupancyId: number; selectionId: string;
  selectionState: string; source: string; submittedAt?: string;
  price: ReturnType<typeof managerPrice>; items: ManagerSelectionItem[];
};
export type ManagerPositionCard = {
  id: number; name: string; type: 'sofa' | 'bed' | 'room'; enabled: boolean;
  association: 'none' | 'unverified' | 'linked'; statusLabel: string;
  detail?: ManagerPositionDetail;
};
export type ManagerPositionMap = { storeId: number; positions: ManagerPositionCard[] };
const occupancyLabels: Record<string, string> = {
  held: '选购中', waiting_service: '待服务', in_service: '服务中',
  post_service_present: '已结束服务 · 待离位确认', cleaning: '已结束服务 · 清洁中',
};
const positionTypeOrder: Record<ManagerPositionCard['type'], number> = { sofa: 0, bed: 1, room: 2 };
function naturalPositionKey(card: ManagerPositionCard): [number, number, string] {
  const number = Number(card.name.match(/\d+/)?.[0]);
  return [positionTypeOrder[card.type], Number.isFinite(number) ? number : Number.MAX_SAFE_INTEGER, card.name];
}
/** 店长座位图按自然编号显示，避免后台 sort_order 与现场编号错位。 */
export function sortManagerPositions(positions: ManagerPositionCard[]): ManagerPositionCard[] {
  return [...positions].sort((left, right) => {
    const [leftType, leftNumber, leftName] = naturalPositionKey(left);
    const [rightType, rightNumber, rightName] = naturalPositionKey(right);
    return leftType - rightType || leftNumber - rightNumber || leftName.localeCompare(rightName, 'zh-CN');
  });
}

/** 床位只按房间号展示，不把 A/B 床拆成两张店长卡片。 */
export function bedRoomLabel(name: string): string {
  const match = name.match(/^(.*?号房间)\s+[AB]\s*床/);
  return match ? match[1] : name;
}

export function groupManagerPositionCards(positions: ManagerPositionCard[]): ManagerPositionCard[] {
  const result: ManagerPositionCard[] = [];
  const bedRooms = new Map<string, ManagerPositionCard>();
  for (const card of positions) {
    if (card.type !== 'bed') {
      result.push(card);
      continue;
    }
    const name = bedRoomLabel(card.name);
    const existing = bedRooms.get(name);
    if (!existing) {
      const grouped = { ...card, name };
      bedRooms.set(name, grouped);
      result.push(grouped);
      continue;
    }
    const linked = [existing, card].find(item => item.detail);
    const candidate = linked
      || (existing.association === 'unverified' || card.association === 'unverified' ? card : existing);
    const merged: ManagerPositionCard = {
      ...candidate,
      name,
      enabled: existing.enabled || card.enabled,
      association: linked ? 'linked' : existing.association === 'unverified' || card.association === 'unverified' ? 'unverified' : 'none',
      statusLabel: linked ? candidate.statusLabel : existing.association === 'unverified' || card.association === 'unverified' ? '关联待核实' : '暂无当前选单',
    };
    bedRooms.set(name, merged);
    const index = result.findIndex(item => item === existing);
    result[index] = merged;
  }
  return result;
}
function object(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
}
function positiveId(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
}
export function projectManagerPositions(value: unknown, storeId: number): ManagerPositionMap {
  const map = object(value);
  if (!positiveId(storeId) || map?.store_id !== storeId || !Array.isArray(map.positions)) {
    throw new Error('当前门店座位数据暂不可用，请重试');
  }
  const ids = new Set<number>();
  const positions = map.positions.map((raw): ManagerPositionCard => {
    const position = object(raw);
    if (!position || !positiveId(position.id) || ids.has(position.id)
      || !['sofa', 'bed', 'room'].includes(String(position.type))) {
      throw new Error('座位数据暂不可用，请重试');
    }
    ids.add(position.id);
    const name = typeof position.customer_label === 'string' && position.customer_label.trim()
      ? position.customer_label : typeof position.name === 'string' && position.name.trim() ? position.name : '未命名服务位';
    const card: ManagerPositionCard = {
      id: position.id, name, type: position.type as ManagerPositionCard['type'],
      enabled: position.operational_status === 'active', association: 'unverified', statusLabel: '关联待核实',
    };
    if (position.occupancy === null && position.selection === null) {
      return { ...card, association: 'none', statusLabel: '暂无当前选单' };
    }
    const occupancy = object(position.occupancy), selection = object(position.selection);
    if (!occupancy || !selection || !positiveId(occupancy.id)
      || occupancy.store_id !== storeId || occupancy.room_id !== position.id || occupancy.active_room_id !== position.id
      || typeof selection.id !== 'string' || !selection.id
      || occupancy.selection_session_id !== selection.id || occupancy.active_session_id !== selection.id
      || typeof occupancy.status !== 'string' || !Object.prototype.hasOwnProperty.call(occupancyLabels, occupancy.status)
      || !Array.isArray(selection.items)) return card;
    const items: ManagerSelectionItem[] = selection.items.map(item => {
      const source = object(item);
      return {
        name: typeof source?.name === 'string' ? source.name : undefined,
        quantity: typeof source?.quantity === 'number' && Number.isSafeInteger(source.quantity) && source.quantity > 0 ? source.quantity : undefined,
        diy_preferences: Array.isArray(source?.diy_preferences) ? source.diy_preferences.filter((entry): entry is string => typeof entry === 'string') : [],
      };
    });
    const status = typeof selection.status === 'string' ? selection.status : '';
    return {
      ...card, association: 'linked', statusLabel: occupancyLabels[occupancy.status],
      detail: {
        positionId: position.id, occupancyId: occupancy.id, selectionId: selection.id,
        selectionState: status === 'draft' ? '选购中' : managerStatusLabel(status),
        source: managerSourceLabel(typeof selection.source === 'string' ? selection.source : undefined),
        submittedAt: typeof selection.submitted_at === 'string' ? selection.submitted_at : undefined,
        price: managerPrice({ status, pricing_snapshot: object(selection.pricing_snapshot) }), items,
      },
    };
  });
  return { storeId, positions: sortManagerPositions(positions) };
}
export function positionDetailMatches(card: ManagerPositionCard | undefined, identity: Pick<ManagerPositionDetail, 'positionId' | 'occupancyId' | 'selectionId'>): boolean {
  return Boolean(card?.detail && card.id === identity.positionId
    && card.detail.occupancyId === identity.occupancyId && card.detail.selectionId === identity.selectionId);
}

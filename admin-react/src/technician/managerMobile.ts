export type ManagerFilter = 'submitted' | 'unassigned' | 'confirmed' | 'all';
export type ManagerSelectionItem = { name?: string; quantity?: number; diy_preferences?: string[] };
export type ManagerSelection = {
  id: string; store_id: number; source: string; status: string; device_label?: string;
  customer: { id: number; nickname?: string; phone?: string; is_member?: boolean } | null;
  items: ManagerSelectionItem[]; submitted_at?: string; created_at?: string;
  pricing_snapshot?: { payable_total_cents?: unknown; applied_price_type?: unknown } | null;
  position?: { occupancy_id: number; room_id: number; name: string; status: string } | null;
  needs_position_assignment: boolean;
  workflow_state?: 'new' | 'waiting_service' | 'in_service' | 'post_service' | 'completed' | 'cancelled';
  workflow_label?: string;
  feedback?: { id: number; rating: number; tags?: string[]; note?: string } | null;
};
export type ManagerChange = {
  id: string; state: string; reason?: string; created_at?: string;
  selection: { id: string; source: string; device_label?: string; status: string };
  revision: { id: string; revision_no: number; added_items: ManagerSelectionItem[]; pricing: unknown };
};
export type ManagerPage = { items: ManagerSelection[]; total: number; page: number; page_size: number };
export const MANAGER_PAGE_SIZE = 20;
export const MANAGER_FILTERS: { value: ManagerFilter; label: string }[] = [
  { value: 'submitted', label: '待确认' }, { value: 'unassigned', label: '待配位' },
  { value: 'confirmed', label: '已确认' }, { value: 'all', label: '全部' },
];
export function isMobileManager(staff: { role?: string; store_id?: number | null; technician_id?: number | null } | null | undefined): boolean {
  return staff?.role === 'manager' && Number.isInteger(staff.store_id) && Number(staff.store_id) > 0;
}
export function managerListParams(filter: ManagerFilter, page: number) {
  return { status: filter === 'all' || filter === 'unassigned' ? undefined : filter,
    needs_position_assignment: filter === 'unassigned' ? true : undefined,
    page: Math.max(1, Math.trunc(page) || 1), page_size: MANAGER_PAGE_SIZE };
}
export function managerSourceLabel(source?: string): string {
  return ({ in_store: '到店选单', mini_program: '顾客手机', personal_qr: '顾客扫码',
    room_qr: '座位扫码', store_qr: '门店扫码', bound_qr: '座位扫码',
    tablet: '门店平板', kiosk: '门店平板' } as Record<string, string>)[source || ''] || '其他门店入口';
}
export function managerStatusLabel(status?: string): string {
  return ({ submitted: '待确认', confirmed: '已确认', cancelled: '已取消', expired: '已过期' } as Record<string, string>)[status || ''] || '状态待核实';
}
/** 店长只读订单视图：提交后由系统归单，不再要求店长确认。 */
export function managerOrderStatusLabel(status?: string): string {
  return ({ submitted: '新订单', confirmed: '已确认', cancelled: '已取消', expired: '已过期' } as Record<string, string>)[status || ''] || '状态待核实';
}
export function managerWorkflowLabel(selection: Pick<ManagerSelection, 'status' | 'workflow_label'>): string {
  return selection.workflow_label || managerOrderStatusLabel(selection.status);
}
export function managerWorkflowColor(selection: Pick<ManagerSelection, 'status' | 'workflow_state'>): string | undefined {
  if (selection.workflow_state === 'in_service') return 'green';
  if (selection.workflow_state === 'post_service') return 'blue';
  if (selection.workflow_state === 'new' || selection.status === 'submitted') return 'gold';
  if (selection.workflow_state === 'cancelled') return 'default';
  return undefined;
}
export function managerPrice(selection: Pick<ManagerSelection, 'status' | 'pricing_snapshot'>) {
  const snapshot = selection.pricing_snapshot;
  const cents = snapshot?.payable_total_cents;
  const priceType = ({ member: '会员价', group: '团购价', store: '门店价' } as Record<string, string>)[String(snapshot?.applied_price_type || '')];
  const label = selection.status === 'submitted' ? '预计金额' : selection.status === 'confirmed' ? '已确认金额' : '本单金额';
  if (!Number.isSafeInteger(cents) || Number(cents) < 0 || !priceType) return { label, value: '金额待核实', priceType: '' };
  const amount = Number(cents);
  return { label, value: '¥' + (amount % 100 === 0 ? String(amount / 100) : (amount / 100).toFixed(2)), priceType };
}
export function managerSelectionActions(selection: Pick<ManagerSelection, 'status' | 'needs_position_assignment'>) {
  const active = selection.status === 'submitted' || selection.status === 'confirmed';
  return { confirm: selection.status === 'submitted', cancel: active, assign: active && selection.needs_position_assignment === true };
}
export function readManagerPage(value: unknown, storeId: number): ManagerPage {
  const page = value as ManagerPage;
  if (!page || !Array.isArray(page.items) || !Number.isInteger(page.total) || page.total < 0
    || !Number.isInteger(page.page) || page.page < 1 || !Number.isInteger(page.page_size) || page.page_size < 1
    || page.items.some(item => !item || typeof item.id !== 'string' || !item.id || item.store_id !== storeId || !Array.isArray(item.items))) {
    throw new Error('选单数据暂不可用，请刷新重试');
  }
  return page;
}
/** 校验企微订单深链返回的单条订单。 */
export function readManagerSelection(value: unknown, storeId: number): ManagerSelection {
  return readManagerPage({ items: [value], total: 1, page: 1, page_size: 1 }, storeId).items[0];
}
export function managerError(error: unknown): { text: string; forbidden: boolean } {
  const response = (error as { response?: { status?: number; data?: { detail?: string | { message?: string } } } })?.response;
  const detail = response?.data?.detail;
  const text = typeof detail === 'string' ? detail : detail?.message;
  return { text: text || (error instanceof Error && !response ? error.message : '操作未完成，请重试'), forbidden: response?.status === 403 };
}
export function createManagerActionRunner() {
  const pending = new Map<string, Promise<unknown>>();
  return {
    run<T>(key: string, request: () => Promise<T>): Promise<T> {
      const existing = pending.get(key);
      if (existing) return existing as Promise<T>;
      const operation = Promise.resolve().then(request).finally(() => { pending.delete(key); });
      pending.set(key, operation);
      return operation;
    },
  };
}

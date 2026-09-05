import type { Addon, Project, SelectionItem } from './domain';
import type { CustomerAuth } from './customerAuth';
import { runTrackedOperation } from './tracking.ts';

export type SelectionSession = {
  id: string;
  store_id: number;
  source: string;
  device_label: string;
  status: 'draft' | 'submitted' | 'confirmed' | 'cancelled' | 'expired';
  items: Array<SelectionItem & { name?: string; category?: string; code?: string }>;
  pricing_snapshot: Record<string, unknown>;
  store_total_cents: number;
  group_total_cents?: number;
  member_total_cents: number;
  expires_at: string | null;
  submitted_at: string | null;
  confirmed_at?: string | null;
  occupancy_status?: Occupancy['status'] | null;
  service_completed_at?: string | null;
  can_evaluate?: boolean;
  evaluated?: boolean;
};

export type SavingHint = {
  kind: 'member' | 'coupon';
  estimated_saving_cents?: number;
  login_required: boolean;
};

export type SelectionQuote = {
  items: SelectionSession['items'];
  pricing: Record<string, unknown>;
  saving_hint: SavingHint | null;
};

export type SelectionRevision = {
  id: string;
  selection_session_id: string;
  revision_no: number;
  state: 'submitted' | 'awaiting_staff_confirmation' | 'confirmed' | 'rejected' | 'superseded';
  snapshot: Record<string, unknown>;
  created_at: string | null;
};

export type Occupancy = {
  id: number;
  store_id: number;
  room_id: number;
  selection_session_id: string;
  active_room_id: number | null;
  status: 'held' | 'waiting_service' | 'in_service' | 'post_service_present' | 'cleaning' | 'released';
  source: string;
  hold_expires_at: string | null;
  version: number;
};

export type ServicePosition = {
  id: number;
  code: string;
  name: string;
  customer_label: string;
  type: 'sofa' | 'room';
  state: 'available' | 'held' | 'waiting_service' | 'in_service' | 'post_service_present' | 'cleaning' | 'unavailable';
  is_current: boolean;
  customer_selectable: boolean;
  operational_status: string;
  map_x: number;
  map_y: number;
  map_width: number;
  map_height: number;
  sort_order: number;
  occupancy: Occupancy | null;
};

export type CouponTemplate = {
  id: number;
  name: string;
  coupon_type: string;
  amount_cents: number;
  percent_off: number;
  min_spend_cents: number;
  validity_days: number;
  daily_claimable: boolean;
  claimable: boolean;
  note: string;
};

export type PageContent = {
  store_id: number;
  page_key: string;
  title: string;
  subtitle: string;
  promo_banners: Array<{ eyebrow?: string; title?: string; image_url?: string; project_code?: string }>;
  tea_options: Array<{ name: string; note?: string; description?: string; image_url?: string }>;
  coupon_prompt: { title?: string; body?: string };
  brand_story: { title?: string; body?: string; image_url?: string };
  published: boolean;
};

export type ServiceStatus = {
  selection_session_id: string;
  occupancy_status: Occupancy['status'] | null;
  service_ended_at: string | null;
  can_evaluate: boolean;
  evaluated: boolean;
};

export type ServiceFeedback = {
  id: number;
  rating: number;
  tags: string[];
  note: string;
  submitted: boolean;
};

export type Order = {
  id: number;
  order_no: string;
  order_type: string;
  status: string;
  pay_status: string;
  pay_amount_cents: number;
  total_amount_cents: number;
  discount_cents: number;
  items: Array<{ name: string; quantity: number; subtotal_cents: number }>;
  booking_date: string | null;
  booking_time: string | null;
  created_at: string;
};

export type MyCoupon = {
  id: number;
  name: string;
  coupon_type: string;
  amount_cents: number;
  percent_off: number;
  min_spend_cents: number;
  status: string;
  claimed_at: string | null;
  expire_at: string | null;
};

export class ApiError extends Error {
  status: number;
  code: string;
  detail: Record<string, unknown>;

  constructor(status: number, message: string, code = '', detail: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail = payload.detail;
    const message = typeof detail === 'string' ? detail : detail?.message || '请求失败，请稍后重试';
    throw new ApiError(
      response.status,
      message,
      typeof detail === 'object' ? detail?.code : '',
      typeof detail === 'object' && detail ? detail : {},
    );
  }
  return response.json() as Promise<T>;
}

export async function getProjects(storeId: number): Promise<Project[]> {
  const result = await request<{ items: Project[] }>(`/projects?store_id=${storeId}`);
  return result.items;
}

export async function getAddons(storeId: number): Promise<Addon[]> {
  return request<Addon[]>(`/addons?store_id=${storeId}&sale_mode=attach`);
}

export function getPageContent(storeId: number, pageKey = 'diy-home') {
  return request<PageContent>(`/stores/${storeId}/page-content?page_key=${encodeURIComponent(pageKey)}`);
}

export async function getCouponTemplates(token = ''): Promise<CouponTemplate[]> {
  const result = await request<{ items: CouponTemplate[] }>('/coupons/templates', token ? {
    headers: { Authorization: `Bearer ${token}` },
  } : {});
  return result.items;
}

export function sendPhoneCode(phone: string) {
  return runTrackedOperation('phone_code_send', {}, () => request<{ sent: boolean; expires_in_seconds: number; debug_code?: string | null }>('/auth/h5/send-code', {
    method: 'POST', body: JSON.stringify({ phone }),
  }));
}

export function loginByPhone(phone: string, code: string, selectionSessionId?: string, selectionToken?: string) {
  return runTrackedOperation('phone_login', { selection_session_id: selectionSessionId || '' }, () => request<CustomerAuth>('/auth/h5/login', {
    method: 'POST',
    headers: selectionToken ? { 'X-Selection-Token': selectionToken } : undefined,
    body: JSON.stringify({ phone, code, selection_session_id: selectionSessionId || null }),
  }));
}

/** 使用仍有效的登录令牌刷新用户快照，避免后台开通会员后 H5 继续使用旧身份。 */
export function getCurrentCustomer(token: string) {
  return request<import('./customerAuth').CustomerUser>('/auth/h5/me', {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function claimCoupon(templateId: number, token: string) {
  return request<{ code: number; name: string }>('/coupons/claim', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ template_id: templateId }),
  });
}

export async function getMyOrders(token: string): Promise<Order[]> {
  return request<Order[]>('/orders', {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function getMyCoupons(token: string): Promise<MyCoupon[]> {
  const result = await request<{ items: MyCoupon[] }>('/coupons', {
    headers: { Authorization: `Bearer ${token}` },
  });
  return result.items;
}

export async function getMySelectionSessions(token: string): Promise<SelectionSession[]> {
  const result = await request<{ items: SelectionSession[] }>('/selection-sessions/mine', {
    headers: { Authorization: `Bearer ${token}` },
  });
  return result.items;
}

export function cancelOrder(orderId: number, token: string) {
  return request<{ code: number; status: string }>(`/orders/${orderId}/cancel`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function createEntrySession(input: {
  store_id: number;
  position_code: string;
  source: string;
  device_label: string;
  entry_token?: string;
  start_new_after_service?: boolean;
}) {
  return runTrackedOperation('position_select', {
    store_id: input.store_id,
    position_code: input.position_code,
    source: input.source,
  }, () => request<{
    session: SelectionSession;
    occupancy: Occupancy;
    position: ServicePosition;
    access_token: string;
  }>('/entry-sessions', { method: 'POST', body: JSON.stringify(input) }));
}

export function getSelectionSession(sessionId: string, token: string) {
  return request<SelectionSession>(`/selection-sessions/${sessionId}`, {
    headers: { 'X-Selection-Token': token },
  });
}

export function saveSelectionSession(sessionId: string, token: string, items: SelectionItem[], deviceLabel: string) {
  return request<SelectionSession>(`/selection-sessions/${sessionId}`, {
    method: 'PATCH',
    headers: { 'X-Selection-Token': token },
    body: JSON.stringify({ items, diy_preferences: {}, device_label: deviceLabel }),
  });
}

export function submitSelectionSession(sessionId: string, token: string, items: SelectionItem[], deviceLabel: string) {
  return request<SelectionSession>(`/selection-sessions/${sessionId}/submit`, {
    method: 'POST',
    headers: { 'X-Selection-Token': token },
    body: JSON.stringify({ items, diy_preferences: {}, device_label: deviceLabel }),
  });
}

export function quoteSelectionSession(sessionId: string, token: string, items: SelectionItem[], deviceLabel: string) {
  return request<SelectionQuote>(`/selection-sessions/${sessionId}/quote`, {
    method: 'POST',
    headers: { 'X-Selection-Token': token },
    body: JSON.stringify({ items, diy_preferences: {}, device_label: deviceLabel }),
  });
}

export function bindSelectionCustomer(sessionId: string, selectionToken: string, authToken: string) {
  return request<{ selection_session_id: string; customer_id: number }>(`/selection-sessions/${sessionId}/bind-customer`, {
    method: 'POST',
    headers: {
      'X-Selection-Token': selectionToken,
      Authorization: `Bearer ${authToken}`,
    },
  });
}

export function submitSelectionRevision(sessionId: string, token: string, items: SelectionItem[], deviceLabel: string) {
  return runTrackedOperation('selection_submit', {
    selection_session_id: sessionId,
    item_count: items.length,
  }, () => request<SelectionRevision>(`/selection-sessions/${sessionId}/revisions`, {
    method: 'POST',
    headers: { 'X-Selection-Token': token, 'Idempotency-Key': crypto.randomUUID() },
    body: JSON.stringify({ items, diy_preferences: {}, device_label: deviceLabel }),
  }));
}

export function getServicePositionMap(storeId: number, sessionId?: string, token?: string) {
  const query = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
  return request<{ store_id: number; positions: ServicePosition[] }>(
    `/stores/${storeId}/service-position-map${query}`,
    token ? { headers: { 'X-Selection-Token': token } } : {},
  );
}

export function moveOccupancy(occupancyId: number, token: string, targetRoomId: number, version: number) {
  return runTrackedOperation('position_move', {
    occupancy_id: occupancyId,
    target_position_id: targetRoomId,
  }, () => request<Occupancy>(`/occupancies/${occupancyId}/move`, {
    method: 'POST',
    headers: { 'X-Selection-Token': token },
    body: JSON.stringify({ target_room_id: targetRoomId, version, reason: '顾客核对服务位' }),
  }));
}

export function getServiceStatus(sessionId: string, token: string) {
  return request<ServiceStatus>(`/selection-sessions/${sessionId}/service-status`, {
    headers: { 'X-Selection-Token': token },
  });
}

export function submitFeedback(sessionId: string, token: string, input: { rating: number; tags: string[]; note: string }) {
  return runTrackedOperation('feedback_submit', {
    selection_session_id: sessionId,
    rating: input.rating,
    tag_count: input.tags.length,
  }, () => request<ServiceFeedback>(`/selection-sessions/${sessionId}/feedback`, {
    method: 'POST',
    headers: { 'X-Selection-Token': token },
    body: JSON.stringify(input),
  }));
}

export function enrollTrustedDevice(token: string) {
  return request<{ trusted: boolean }>('/auth/h5/trusted-device/enroll', { method: 'POST', headers: { Authorization: `Bearer ${token}` } });
}

export function issueMemberCode(token: string) {
  return request<{ code_token: string; expires_at: string }>('/auth/h5/member-code', { method: 'POST', headers: { Authorization: `Bearer ${token}` } });
}

export function submitCustomerFeedback(sessionId: string, token: string, input: { rating: number; tags: string[]; note: string }) {
  return runTrackedOperation('feedback_submit', { selection_session_id: sessionId, rating: input.rating, tag_count: input.tags.length }, () => request<ServiceFeedback>(`/selection-sessions/${sessionId}/feedback`, {
    method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: JSON.stringify(input),
  }));
}

import axios from 'axios';
import type { LiveServicePositionMap, PositionOccupancy } from './servicePositions.ts';
import { getEntryLoginPath, isTechnicianEntry } from './auth.ts';
import type { TechnicianServiceReferenceResponse } from './technician/serviceReference.ts';

const API = '/api/v1/admin';
const API2 = '/api/v1/admin/v2';

export const client = axios.create({ baseURL: '/api/v1' });

let apiErrorHandler: (message: string) => void = () => undefined;

export function setApiErrorHandler(handler: (message: string) => void) {
  apiErrorHandler = handler;
}

// Token management
const getToken = () => localStorage.getItem('hxy_admin_token') || '';
const getStaff = () => {
  try { return JSON.parse(localStorage.getItem('hxy_admin_staff') || 'null'); } catch { return null; }
};

client.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : detail?.message || '账号不可用，请联系店长';
      localStorage.removeItem('hxy_admin_token');
      localStorage.removeItem('hxy_admin_staff');
      if (err.config?.url?.includes('/admin/login') || err.config?.url?.includes('/technician/activate')) {
        apiErrorHandler(msg);
        return Promise.reject(err);
      }
      if (isTechnicianEntry()) {
        window.location.replace(getEntryLoginPath(true));
      } else {
        window.location.hash = '#/login';
      }
      return Promise.reject(err);
    }
    const detail = err.response?.data?.detail;
    const msg = typeof detail === 'string' ? detail : detail?.message || '请求失败';
    apiErrorHandler(msg);
    return Promise.reject(err);
  }
);

// Auth
export const login = (username: string, password: string) =>
  client.post('/admin/login', { username, password });

export const getTechnicianMe = () => client.get('/technician/me');
export const getTechnicianTasks = () => client.get('/technician/tasks');
export const getTechnicianServiceReference = (occupancyId: number) =>
  client.get<TechnicianServiceReferenceResponse>(`/technician/occupancies/${occupancyId}/service-reference`);
export const getTechnicianServiceHistory = (page = 1, pageSize = 20, profileStatus: 'all' | 'confirmed' | 'pending' = 'all') =>
  client.get('/technician/service-history', { params: { page, page_size: pageSize, profile_status: profileStatus } });
export const getTechnicianServiceOrders = (status: 'in_progress' | 'history' = 'in_progress', page = 1, pageSize = 30) =>
  client.get('/admin/v2/service-orders', { params: { status, page, page_size: pageSize } });
export const createProfileRecord = (customerId: number, data: { tags: string[]; service_note: string }, idempotencyKey?: string) =>
  client.post(`/admin/v2/customers/${customerId}/profile-records`, data, {
    headers: { 'Idempotency-Key': idempotencyKey || (globalThis.crypto?.randomUUID?.() || `legacy-profile-${Date.now()}`) },
  });
export const submitTechnicianLeave = (data: { start_date: string; end_date: string; reason: string }) => client.post('/technician/leave-requests', data);
export const confirmTechnicianService = (occupancyId: number, idempotencyKey: string) => client.post(`/technician/occupancies/${occupancyId}/confirm`, { idempotency_key: idempotencyKey });
export const finishTechnicianService = (occupancyId: number, idempotencyKey: string) => client.post(`/technician/occupancies/${occupancyId}/finish`, { idempotency_key: idempotencyKey });

export const getTodayStats = () => client.get('/admin/stats');
export const checkIn = (id: number) => client.post(`/admin/orders/${id}/check-in`);
export const complete = (id: number) => client.post(`/admin/orders/${id}/complete`);

// Live store operations. The server owns every state transition.
export const getLiveBoard = () => client.get('/operations/live-board');
export const operationCheckIn = (orderId: number, idempotencyKey: string) =>
  client.post(`/operations/orders/${orderId}/check-in`, { idempotency_key: idempotencyKey });
export const readyService = (serviceOrderId: number, idempotencyKey: string) =>
  client.post(`/operations/service-orders/${serviceOrderId}/ready`, { idempotency_key: idempotencyKey });
export const startService = (serviceOrderId: number, idempotencyKey: string) =>
  client.post(`/operations/service-orders/${serviceOrderId}/start`, { idempotency_key: idempotencyKey });
export const finishService = (serviceOrderId: number, idempotencyKey: string) =>
  client.post(`/operations/service-orders/${serviceOrderId}/finish`, { idempotency_key: idempotencyKey });
export const settleService = (serviceOrderId: number, idempotencyKey: string) =>
  client.post(`/operations/service-orders/${serviceOrderId}/settle`, {
    idempotency_key: idempotencyKey,
    payment_method: 'prepaid',
    received_amount_cents: 0,
    payment_reference: '',
  });

// Orders
export const getOrders = (status?: string) => client.get('/admin/orders', { params: { status } });
export const getSelectionSessions = (status?: string) => client.get('/admin/v2/selection-sessions', { params: { status } });
export const getCustomerProfileRecords = (userId: number) => client.get(`/admin/v2/users/${userId}/customer-profile-records`);
export const createCustomerProfileRecord = (data: {
  user_id: number;
  selection_session_id?: string;
  technician_id?: number;
  source?: 'customer_statement' | 'service_observation' | 'both';
  schema_version?: 1 | 2 | 3;
  taxonomy_version?: 'service_reference_v1' | 'service_reference_v2';
  customer_confirmed?: boolean;
  profile: Record<string, unknown>;
  signals: string[];
  note: string;
  correction_of_id?: number;
  correction_reason?: string;
}, idempotencyKey?: string) => client.post('/admin/v2/customer-profile-records', data, {
  headers: { 'Idempotency-Key': idempotencyKey || (globalThis.crypto?.randomUUID?.() || `profile-${Date.now()}-${Math.random().toString(36).slice(2)}`) },
});
export const confirmSelectionSession = (id: string) => client.post(`/admin/v2/selection-sessions/${id}/confirm`);
export const cancelSelectionSession = (id: string) => client.post(`/admin/v2/selection-sessions/${id}/cancel`);
export const getSelectionChangeRequests = (state = 'awaiting_staff_confirmation') =>
  client.get('/admin/v2/selection-change-requests', { params: { state } });
export const approveSelectionChangeRequest = (id: string) =>
  client.post(`/admin/v2/selection-change-requests/${id}/approve`);
export const rejectSelectionChangeRequest = (id: string, reason: string) =>
  client.post(`/admin/v2/selection-change-requests/${id}/reject`, { reason });
export const settleSelectionSession = (
  id: string,
  data: {
    idempotency_key: string;
    payment_method: string;
    received_amount_cents: number;
    payment_reference: string;
    reason?: string;
    service_adjustment_cents?: number;
    adjustment_reason_code?: string;
    responsibility?: string;
  },
) => client.post(`/operations/selection-sessions/${id}/settle`, data);
export const registerRefundNote = (
  orderId: number,
  data: {
    idempotency_key: string;
    amount_cents: number;
    reason_code: string;
    responsibility: string;
    refund_reference: string;
    reason: string;
  },
) => client.post(`/operations/orders/${orderId}/refund-note`, data);

// 顾客到店 DIY 选单，不创建订单、不涉及支付。
export const getLiveServicePositionMap = () =>
  client.get<LiveServicePositionMap>('/admin/live-service-position-map');
export const createKioskSession = (roomId: number, deviceLabel = '共享 iPad') =>
  client.post('/admin/kiosk-sessions', { room_id: roomId, device_label: deviceLabel });
export type PositionQr = {
  qr_id: number;
  store_id: number;
  room_id: number;
  position_code: string;
  position_name: string;
  source: string;
  status: 'active' | 'disabled';
  token: string;
  url: string;
  last_accessed_at: string | null;
  created_at: string | null;
};
export const getPositionQrLink = (roomId: number) =>
  client.get<PositionQr>(`/admin/service-positions/${roomId}/qr-link`);
export const updateServicePositionOperationalStatus = (roomId: number, operationalStatus: 'active' | 'inactive', reason: string) =>
  client.patch(`/admin/service-positions/${roomId}/operational-status`, { operational_status: operationalStatus, reason });
export const updatePositionQr = (qrId: number, status: 'active' | 'disabled', reason: string) =>
  client.patch<PositionQr>(`/admin/service-position-qrs/${qrId}`, { status, reason });
export const regeneratePositionQr = (qrId: number, reason = '重新生成现场二维码') =>
  client.post<PositionQr>(`/admin/service-position-qrs/${qrId}/regenerate`, { reason });
export const rebindPositionQr = (qrId: number, targetRoomId: number, reason: string) =>
  client.post<PositionQr>(`/admin/service-position-qrs/${qrId}/rebind`, { target_room_id: targetRoomId, reason });
export const startPositionService = (occupancyId: number, expectedMinutes = 60) =>
  client.post<PositionOccupancy>(`/admin/occupancies/${occupancyId}/start-service`, { expected_minutes: expectedMinutes });
export const finishPositionService = (occupancyId: number) =>
  client.post<PositionOccupancy>(`/admin/occupancies/${occupancyId}/finish-service`, {});

// Analytics
export const getAnalytics = (days = 7) => client.get('/admin/analytics', { params: { days } });
export const getOperationsSummary = (startDate: string, endDate: string) =>
  client.get('/admin/operations-summary', { params: { start_date: startDate, end_date: endDate } });
export const getAuditLogs = (params: Record<string, string | number | undefined>) =>
  client.get('/admin/audit-logs', { params });
export const exportAuditLogs = (params: Record<string, string | number | undefined>) =>
  client.get('/admin/audit-logs', { params: { ...params, export: true }, responseType: 'blob' });
export const getFeedback = (params?: Record<string, string | number | boolean | undefined>) =>
  client.get('/admin/v2/feedback', { params });
export const updateFeedbackFollowUp = (id: number, data: { follow_up_status: string; follow_up_note: string }) =>
  client.patch(`/admin/v2/feedback/${id}`, data);

// Coupons
export const getCoupons = () => client.get('/admin/coupons');
export const createCoupon = (data: any) => client.post('/admin/coupons', data);
export const toggleCouponStatus = (id: number, status: string) =>
  client.post(`/admin/coupons/${id}`, { status });

// Rooms
export const getStoreMasterData = (params?: any) => client.get('/admin/v2/stores', { params });
export const createStoreMasterData = (data: any) => client.post('/admin/v2/stores', data);
export const updateStoreMasterData = (id: number, data: any) => client.patch(`/admin/v2/stores/${id}`, data);
export const getRooms = (params?: any) => client.get('/admin/v2/rooms', { params });
export const createRoom = (data: any) => client.post('/admin/v2/rooms', data);
export const deleteRoom = (id: number) => client.delete(`/admin/v2/rooms/${id}`);
export const getRoomStats = () => client.get('/admin/v2/rooms/stats');
export const operateRoom = (id: number, data: { action: string; technician_id?: number; note?: string }) =>
  client.post(`/admin/v2/rooms/${id}/operate`, data);

// Technicians
export const getTechnicians = (params?: any) => client.get('/admin/v2/technicians', { params });
export const createTechnician = (data: any) => client.post('/admin/v2/technicians', data);

const lifecycleIdempotencyKey = (action: string, id: number) => {
  const random = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${action}:${id}:${random}`.slice(0, 128);
};

const lifecycleRequestConfig = (action: string, id: number, idempotencyKey?: string) => ({
  headers: { 'Idempotency-Key': idempotencyKey || lifecycleIdempotencyKey(action, id) },
});

export const inviteTechnician = (id: number, idempotencyKey?: string) =>
  client.post(`/admin/v2/technicians/${id}/invite`, undefined, lifecycleRequestConfig('invite', id, idempotencyKey));
export const activateTechnician = (token: string, password: string) =>
  client.post('/technician/activate', { token, password });
export const resetTechnicianLogin = (id: number, idempotencyKey?: string) =>
  client.post(`/admin/v2/technicians/${id}/reset-login`, undefined, lifecycleRequestConfig('reset-login', id, idempotencyKey));
export const disableTechnicianLogin = (id: number, idempotencyKey?: string) =>
  client.post(`/admin/v2/technicians/${id}/disable`, undefined, lifecycleRequestConfig('disable', id, idempotencyKey));
export const restoreTechnicianLogin = (id: number, idempotencyKey?: string) =>
  client.post(`/admin/v2/technicians/${id}/restore`, undefined, lifecycleRequestConfig('restore', id, idempotencyKey));
export const rehireTechnician = (id: number, idempotencyKey?: string) =>
  client.post(`/admin/v2/technicians/${id}/rehire`, undefined, lifecycleRequestConfig('rehire', id, idempotencyKey));
export const resignTechnician = (id: number, reason: string, idempotencyKey?: string) =>
  client.post(`/admin/v2/technicians/${id}/resign`, { reason }, lifecycleRequestConfig('resign', id, idempotencyKey));
export const getTechnicianLeaveRequests = (status?: string) => client.get('/admin/v2/technician-leave-requests', { params: { status } });
export const approveTechnicianLeave = (id: number, review_note = '') => client.post(`/admin/v2/technician-leave-requests/${id}/approve`, { review_note });

// Projects
export const getProjectsAdmin = () => client.get('/admin/v2/projects');
export const createProject = (data: any) => client.post('/admin/v2/projects', data);
export const updateProject = (id: number, data: any) => client.post(`/admin/v2/projects/${id}`, data);
export const getAddonsAdmin = (params?: any) => client.get('/admin/v2/addons', { params });
export const createAddon = (data: any) => client.post('/admin/v2/addons', data);
export const updateAddon = (id: number, data: any) => client.post(`/admin/v2/addons/${id}`, data);

export const uploadMedia = (file: File, purpose = 'general', storeId?: number) => {
  const form = new FormData();
  form.append('file', file);
  form.append('purpose', purpose);
  if (storeId !== undefined) form.append('store_id', String(storeId));
  return client.post('/admin/media', form, { headers: { 'Content-Type': 'multipart/form-data' } });
};
export const deleteMedia = (id: number) => client.delete(`/admin/media/${id}`);

// Project catalog options
export const getOptionGroups = (projectId: number) => client.get(`/admin/v2/projects/${projectId}/option-groups`);
export const createOptionGroup = (projectId: number, data: any) => client.post(`/admin/v2/projects/${projectId}/option-groups`, data);
export const updateOptionGroup = (projectId: number, groupId: number, data: any) => client.patch(`/admin/v2/projects/${projectId}/option-groups/${groupId}`, data);
export const deleteOptionGroup = (projectId: number, groupId: number) => client.delete(`/admin/v2/projects/${projectId}/option-groups/${groupId}`);
export const createOptionChoice = (projectId: number, groupId: number, data: any) => client.post(`/admin/v2/projects/${projectId}/option-groups/${groupId}/choices`, data);
export const updateOptionChoice = (projectId: number, groupId: number, choiceId: number, data: any) => client.patch(`/admin/v2/projects/${projectId}/option-groups/${groupId}/choices/${choiceId}`, data);
export const deleteOptionChoice = (projectId: number, groupId: number, choiceId: number) => client.delete(`/admin/v2/projects/${projectId}/option-groups/${groupId}/choices/${choiceId}`);
export const copyOptionGroups = (projectId: number, sourceProjectId: number) => client.post(`/admin/v2/projects/${projectId}/option-groups/copy-from/${sourceProjectId}`);
export const validateCatalogPublication = (projectId: number) => client.get(`/admin/v2/projects/${projectId}/validate-publication`);
export const publishCatalog = (projectId: number) => client.post(`/admin/v2/projects/${projectId}/publish`);
export const getCatalogVersions = (projectId: number) => client.get(`/admin/v2/projects/${projectId}/versions`);
export const previewCatalogPrice = (projectId: number, data: { choice_ids: number[]; is_member: boolean; confirmed_at: string; store_timezone: string }) => client.post(`/admin/v2/projects/${projectId}/price-preview`, data);

export const getPageContent = (pageKey = 'diy-home') => client.get('/admin/v2/page-content', { params: { page_key: pageKey } });
export const updatePageContent = (pageKey: string, data: any) => client.put('/admin/v2/page-content', data, { params: { page_key: pageKey } });

// Products
export const getProductsAdmin = () => client.get('/admin/v2/products');
export const createProduct = (data: any) => client.post('/admin/v2/products', data);

// Tags
export const getTags = () => client.get('/admin/v2/tags');
export const createTag = (data: any) => client.post('/admin/v2/tags', data);
export const deleteTag = (id: number) => client.delete(`/admin/v2/tags/${id}`);

// Users
export const getUsers = (params?: any) => client.get('/admin/v2/users', { params });
export const addUserTag = (userId: number, tagId: number) =>
  client.post(`/admin/v2/users/${userId}/tags`, { tag_id: tagId });
export const setUserMembership = (userId: number, isMember: boolean) => {
  if (!isMember) return client.patch(`/admin/v2/users/${userId}/membership`, { is_member: false });
  const started = new Date();
  const expire = new Date(started);
  expire.setFullYear(expire.getFullYear() + 1);
  return client.patch(`/admin/v2/users/${userId}/membership`, {
    member_type: 'annual',
    cycle_id: `manual-${userId}-${started.getTime()}`,
    member_started_at: started.toISOString(),
    member_expire_at: expire.toISOString(),
  });
};

// Segments
export const getSegments = () => client.get('/admin/v2/segments');
export const createSegment = (data: any) => client.post('/admin/v2/segments', data);
export const recountSegment = (id: number) => client.post(`/admin/v2/segments/${id}/recount`);

// Automations
export const getAutomations = () => client.get('/admin/v2/automations');
export const createAutomation = (data: any) => client.post('/admin/v2/automations', data);
export const updateAutomation = (id: number, data: any) => client.post(`/admin/v2/automations/${id}`, data);
export const deleteAutomationRule = (id: number) => client.delete(`/admin/v2/automations/${id}`);

export { getToken, getStaff };

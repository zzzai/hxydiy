
import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom/client';
import { App, ConfigProvider } from 'antd';
import { AxiosError } from 'axios';
import { client, getStaff } from '../src/api';
import { commitStaffSession, getSessionEpoch } from '../src/wecomSession';
import { writeStaffSession } from '../src/staffSession';
import TechnicianMobileApp from '../src/technician/TechnicianMobileApp';

const params = new URLSearchParams(location.search);
const scenario = params.get('scenario') || 'normal';
const technician = { id: 7, role: 'technician', technician_id: 7, store_id: 1, name: '合成技师', store_name: '合成门店' };
const manager = { id: 3, role: 'manager', technician_id: null, store_id: 1, name: '合成店长', store_name: '合成门店' };
const callback = scenario === 'callback' || scenario === 'callback-wait';
if (params.has('reset') || !sessionStorage.getItem('manager-fixture-ready')) {
  for (const key of ['hxy_admin_token', 'hxy_admin_staff', 'hxy_staff_auth_method', 'hxy_technician_token', 'hxy_technician_staff', 'hxy_technician_auth_method']) localStorage.removeItem(key);
  sessionStorage.removeItem('hxy_wecom_pending');
  writeStaffSession(localStorage, { token: 'synthetic-technician', staff: technician, authMethod: 'wecom' });
  if (!callback && scenario !== 'technician') writeStaffSession(localStorage, { token: 'synthetic-manager', staff: manager, authMethod: 'wecom' });
  if (callback) sessionStorage.setItem('hxy_wecom_pending', JSON.stringify({ entry_nonce: 'synthetic-nonce', attempt_id: 'synthetic-attempt', entry_path: '/technician/store/wecom' }));
  sessionStorage.setItem('manager-fixture-ready', '1');
  params.delete('reset');
  history.replaceState(null, '', location.pathname + '?' + params);
}
const stats = { reads: 0, writes: 0, technicianCalls: 0, unexpected: 0, oldReadReleased: false, mapReads: 0, mapPending: false, mapReleased: false };
const entries = Array.from({ length: 42 }, (_, i) => ({
  id: 'synthetic-selection-' + String(i + 1).padStart(4, '0'), store_id: 1,
  status: i < 27 ? 'submitted' : i < 36 ? 'confirmed' : 'cancelled',
  source: i % 2 ? 'personal_qr' : 'in_store', device_label: 'Synthetic device',
  customer: i % 3 ? null : { id: i + 1, nickname: '合成顾客' + (i + 1), phone: '138****0000', is_member: true },
  items: [{ name: i === 0 ? '招牌草本泡与肩颈背部放松服务（合成长项目名称）' : '招牌草本泡', quantity: 1 }, ...(i === 0 ? [{ name: '头疗', quantity: 1 }] : [])],
  pricing_snapshot: i === 2 ? null : { payable_total_cents: i === 1 ? 0 : 8900, applied_price_type: 'member' },
  submitted_at: '2026-10-20T10:00:00+08:00', created_at: '2026-10-20T09:58:00+08:00',
  needs_position_assignment: i % 2 === 0 && i < 36,
  position: i % 2 ? { room_id: i + 1, occupancy_id: i + 1, name: (i + 1) + '号沙发', status: 'in_service' } : null,
}));
const changes = [28, 29].map(n => ({ id: 'synthetic-change-' + n, state: 'awaiting_staff_confirmation',
  created_at: '2026-10-20T10:05:00+08:00',
  selection: { id: entries[n].id, source: entries[n].source, status: entries[n].status },
  revision: { id: 'synthetic-revision-' + n, revision_no: 2, added_items: [{ name: '头疗', quantity: 1 }], pricing: {} },
}));

let mapRevision = 0, holdNextMap = false, mapFailure = scenario === 'positions-error';
let releaseMap: (() => void) | undefined;
function positionFixture(storeId: number) {
  const total = scenario.startsWith('positions') ? 25 : 3;
  return Array.from({ length: total }, (_, i) => {
    const n = i + 1, id = 100 + n;
    const type = [4, 6, 7, 9].includes(n) ? 'bed' : [5, 8].includes(n) ? 'room' : 'sofa';
    const name = (storeId === 2 ? '二店·' : '') + n + (type === 'bed' ? '号床位' : type === 'room' ? '号房间' : '号沙发');
    const status = n === 4 ? 'post_service_present' : n === 5 ? 'cleaning' : n === 10 ? 'held' : n === 11 ? 'waiting_service' : 'in_service';
    const assigned = n === 1 && entries[0].position?.room_id === 101 && !entries[0].needs_position_assignment;
    const linked = assigned || (n >= 2 && n <= 11);
    const selectionId = assigned ? entries[0].id : 'synthetic-position-' + id + (n === 2 && mapRevision ? '-changed' : '');
    const selection = linked ? {
      id: selectionId, status: assigned ? entries[0].status : 'confirmed', source: 'in_store',
      items: assigned ? entries[0].items : [{ name: n === 8 || n === 9 ? '不应展示的错误关联项目' : n === 2 && mapRevision ? '新关联选单项目' : n === 2 ? '招牌草本泡与肩颈背部放松服务（合成长项目名称）' : '草本泡', quantity: 1, diy_preferences: ['肩颈多按一会'] }],
      pricing_snapshot: n === 7 ? null : { payable_total_cents: n === 6 ? 0 : 8900, applied_price_type: 'member' },
    } : null;
    return {
      id, name, customer_label: name, type, sort_order: n,
      state: assigned ? 'waiting_service' : linked ? status : 'available', operational_status: n === 3 ? 'maintenance' : 'active',
      occupancy: linked ? { id: 500 + n + (n === 2 ? mapRevision * 1000 : 0), store_id: storeId, room_id: id, active_room_id: n === 8 ? 999 : id,
        selection_session_id: selectionId, active_session_id: n === 9 ? undefined : selectionId, status: assigned ? 'waiting_service' : status } : null,
      selection,
    };
  });
}

let holdNextRead = false;
let releaseOld: (() => void) | undefined;
let completeCallback: (() => void) | undefined;
const wait = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
client.defaults.adapter = async config => {
  const path = config.url || '';
  const method = (config.method || 'get').toLowerCase();
  const fail = (status: number, message: string): never => {
    throw new AxiosError(message, 'SYNTHETIC_' + status, config, undefined, { status, statusText: 'Synthetic', headers: {}, config, data: { detail: { message } } });
  };
  const ok = (data: unknown) => ({ data: JSON.parse(JSON.stringify(data)), status: 200, statusText: 'OK', headers: {}, config });
  if (path.startsWith('/technician/')) {
    ++stats.technicianCalls;
    if (getStaff()?.role !== 'technician') { ++stats.unexpected; return fail(403, '合成守卫：禁止店长调用技师接口'); }
    if (path === '/technician/me') return ok({ staff: technician, technician: { id: 7, name: '合成技师' } });
    if (path === '/technician/my-tasks') return ok({ items: [] });
    ++stats.unexpected; return fail(403, '合成守卫：未列入白名单');
  }
  if (path === '/admin/login') return ok({ token: 'synthetic-manager', staff: { ...manager, role: 'store_manager' }, workspaces: [], selector_token: null });
  if (scenario === 'expired') return fail(401, '合成会话已失效');
  if (method === 'get' && path === '/admin/v2/service-anomalies') return ok({ items: [], total: 0 });
  if (method === 'get' && ['/admin/exceptions', '/admin/v2/feedback'].includes(path)) return ok({ items: [] });
  if (method === 'get' && path === '/admin/v2/manager/unassigned-services') return ok({ items: [], total: 0 });
  if (method === 'get' && path === '/admin/v2/manager/workbench') return ok({
    record_follow_up: { window_days: 30, pending_count: 0, technicians: [] },
    store_id: 1,
    generated_at: '2026-10-21T00:00:00Z',
    summary: { today_orders: scenario === 'empty' ? 0 : 3, in_service: scenario === 'empty' ? 0 : 1, pending_checkout: scenario === 'empty' ? 0 : 1, attention: scenario === 'empty' ? 0 : 1 },
    attention: scenario === 'empty' ? [] : [{ key: 'addon', label: '顾客加选待处理', count: 1 }],
  });
  if (method === 'get' && path === '/admin/v2/selection-sessions') {
    ++stats.reads;
    if (scenario === 'error') return fail(503, '合成网络错误，请重试');
    const query = config.params || {}, page = Number(query.page || 1), page_size = Number(query.page_size || 20);
    const filtered = scenario === 'empty' ? [] : entries.filter(item => (!query.status || item.status === query.status) && (!query.needs_position_assignment || item.needs_position_assignment) && (!query.active_only || ['submitted', 'confirmed'].includes(item.status)));
    const response = ok({ items: filtered.slice((page - 1) * page_size, page * page_size).map(item => ({ ...item, store_id: getStaff()?.store_id || 1 })), total: filtered.length, page, page_size });
    if (scenario === 'race' && holdNextRead) {
      holdNextRead = false;
      await new Promise<void>(resolve => { releaseOld = () => { stats.oldReadReleased = true; resolve(); }; });
    }
    return response;
  }
  if (method === 'get' && path === '/admin/v2/selection-change-requests') return ok({ items: scenario === 'empty' ? [] : changes.filter(item => item.state === 'awaiting_staff_confirmation'), total: scenario === 'empty' ? 0 : changes.filter(item => item.state === 'awaiting_staff_confirmation').length });
  if (method === 'get' && path === '/admin/live-service-position-map') {
    ++stats.mapReads;
    if (mapFailure) return fail(503, '合成座位请求失败');
    const storeId = Number(getStaff()?.store_id || 1);
    const response = ok({ store_id: scenario === 'positions-wrong-store' ? 99 : storeId,
      positions: scenario === 'positions-empty' ? [] : positionFixture(storeId) });
    if (holdNextMap) {
      holdNextMap = false; stats.mapPending = true;
      await new Promise<void>(resolve => { releaseMap = () => { stats.mapPending = false; stats.mapReleased = true; resolve(); }; });
    }
    return response;
  }
  if (method === 'post' && path.startsWith('/admin/v2/selection-')) {
    ++stats.writes; await wait(150);
    if (scenario === 'conflict') return fail(409, '合成冲突：服务状态已变化，请核对后重试');
    if (scenario === 'forbidden') return fail(403, '合成权限拒绝');
    const parts = path.split('/'), id = parts[parts.length - 2], action = parts[parts.length - 1];
    const body = typeof config.data === 'string' ? JSON.parse(config.data) : config.data;
    const selection = entries.find(item => item.id === id), change = changes.find(item => item.id === id);
    if (selection) {
      if (action === 'confirm') selection.status = 'confirmed';
      else if (action === 'cancel') selection.status = 'cancelled';
      else if (action === 'assign-position' && body?.room_id === 101) {
        selection.needs_position_assignment = false;
        selection.position = { room_id: 101, occupancy_id: 501, name: '1号沙发', status: 'waiting_service' };
      } else return fail(400, '合成动作参数错误');
      const { position, needs_position_assignment, ...actionResponse } = selection;
      if (releaseOld) { setTimeout(releaseOld, 1500); releaseOld = undefined; }
      return ok(actionResponse);
    }
    if (change) {
      if (action === 'approve') {
        change.state = 'approved';
        const original = entries.find(item => item.id === change.selection.id)!;
        original.pricing_snapshot = { payable_total_cents: 11900, applied_price_type: 'member' };
      } else if (action === 'reject' && body?.reason?.trim()) change.state = 'rejected';
      else return fail(400, '合成拒绝原因不能为空');
      if (releaseOld) { setTimeout(releaseOld, 1500); releaseOld = undefined; }
      return ok(change);
    }
    return fail(404, '合成目标不存在');
  }
  ++stats.unexpected;
  return fail(403, '合成守卫：禁止非白名单请求');
};
globalThis.fetch = async input => {
  const path = String(input);
  if (path === '/api/v1/auth/wecom/exchange') {
    if (scenario === 'callback-wait') await new Promise<void>(resolve => { completeCallback = resolve; });
    else await wait(400);
    return new Response(JSON.stringify({ token: 'synthetic-manager', staff: { ...manager, role: 'store_manager' }, auth_method: 'wecom', selector_token: null, workspaces: [{ assignment_id: 3, role: 'store_manager', scope_type: 'store', scope_id: 1 }] }), { status: 200 });
  }
  if (path === '/api/v1/auth/wecom/authorize') return new Response(JSON.stringify({ detail: '合成环境不连接真实企业微信，请使用合成场景入口' }), { status: 503 });
  ++stats.unexpected;
  throw new Error('Synthetic fixture blocks external fetch');
};
function Fixture() {
  const [, refresh] = useState(0);
  useEffect(() => { const id = setInterval(() => refresh(v => v + 1), 500); return () => clearInterval(id); }, []);
  return <ConfigProvider theme={{ token: { colorPrimary: '#164f3c', borderRadius: 10 } }}><App>
    <aside style={{ padding: '8px 12px', background: '#fff4d9', color: '#57451a', fontSize: 11, overflowWrap: 'anywhere' }}>
      合成预览 · 不连接生产 · {scenario}<br />
      列表读取 {stats.reads} · 操作 {stats.writes} · 技师接口 {stats.technicianCalls} · 非白名单 {stats.unexpected} · 旧读释放 {String(stats.oldReadReleased)} · 座位读取 {stats.mapReads} · 座位挂起 {String(stats.mapPending)} · 座位释放 {String(stats.mapReleased)}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 6 }}>
        <a href="/technician/store?scenario=normal&reset=1">正常</a><a href="/technician/store?scenario=empty&reset=1">空列表</a><a href="/technician/store?scenario=error&reset=1">加载失败</a><a href="/technician/store?scenario=conflict&reset=1">操作冲突</a><a href="/technician/store?scenario=forbidden&reset=1">权限拒绝</a><a href="/technician/store?scenario=race&reset=1">慢读竞态</a><a href="/technician/store?scenario=expired&reset=1">会话失效</a><a href="/technician/wecom/complete?scenario=callback&reset=1">双身份回调</a><a href="/technician/wecom/complete?scenario=callback-wait&reset=1">回调等待</a><a href="/technician/today?scenario=technician&reset=1">技师</a>
        {scenario.startsWith('positions') && <>
          <button onClick={() => { holdNextMap = true; }}>挂起下次座位读取（合成）</button>
          <button onClick={() => { releaseMap?.(); releaseMap = undefined; }}>释放旧座位读取（合成）</button>
          <button onClick={() => { ++mapRevision; }}>更换座位选单（合成）</button>
          <button onClick={() => { mapFailure = false; }}>恢复座位读取（合成）</button>
          <a href="/fixture-left">离开座位（合成）</a>
        </>}
        {scenario === 'race' && <button onClick={() => { holdNextRead = true; }}>挂起下次列表读取（合成）</button>}
        {scenario === 'callback-wait' && <><button onClick={() => completeCallback?.()}>完成回调（合成）</button><a href="/fixture-left">离开回调（合成）</a></>}
        <button onClick={() => commitStaffSession({ token: 'synthetic-manager-2', staff: { ...manager, id: 4, store_id: 2, name: '另一位合成店长', store_name: '合成二店' }, auth_method: 'wecom' }, getSessionEpoch())}>换店长（合成）</button>
      </div>
    </aside>
    <TechnicianMobileApp />
  </App></ConfigProvider>;
}
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><Fixture /></React.StrictMode>);

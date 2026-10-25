import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { App, ConfigProvider } from 'antd';
import { AxiosError } from 'axios';
import { client } from '../src/api';
import { clearStaffSession } from '../src/wecomSession';
import ManagerTasksView from '../src/technician/ManagerTasksView';
import TechnicianServiceHistoryPage from '../src/technician/TechnicianServiceHistoryPage';
import '../src/technician/technician-mobile.css';
import '../src/technician/manager-mobile.css';

const mode = new URLSearchParams(location.search).get('mode') || 'manager';
const stats = { reads: 0, ack: 0, saves: 0, unexpected: 0, filter: '', pending: mode === 'history-last-page' ? 21 : 1 };
let status = mode === 'return' ? 'acknowledged' : 'open', failAck = mode === 'ack-error', failSave = mode === 'save-error';
let release: (() => void) | undefined;
let hold = mode === 'late';
const service = {
  occupancy_id: 101, completed_at: '2026-10-23T10:00:00+08:00', duration_minutes: 30,
  profile_status: 'pending', customer: { display_name: '合成顾客' }, projects: ['合成项目'], service_position: '合成沙发',
  profile_summary: null, record_completed: false,
  record_task: { user_id: 1001, selection_session_id: 'synthetic-closeout', items: [{ name: '合成项目' }], room_name: '合成沙发' },
};
(window as any).closeoutStats = stats;
client.defaults.adapter = async config => {
  const path = config.url, method = config.method;
  const ok = (data: unknown) => ({ data, status: 200, statusText: 'OK', headers: {}, config });
  const fail = () => { throw new AxiosError('Synthetic network failure', 'ERR_NETWORK', config); };
  if (method === 'get') stats.reads++;
  if (path === '/admin/v2/feedback' && method === 'get') return ok({ items: [] });
  if (path === '/admin/v2/manager/service-orders' && method === 'get') return ok({ status: config.params?.status, items: [], total: 0 });
  if (path === '/admin/v2/manager/unassigned-services' && method === 'get') return ok({ items: [], total: 0 });
  if (path === '/admin/v2/manager/workbench' && method === 'get') {
    if (mode === 'load-error') return fail();
    const data = { attention: [], record_follow_up: { pending_count: stats.pending, window_days: 30, technicians: stats.pending ? [{ technician_id: 7, name: '合成技师', count: stats.pending }] : [] } };
    if (hold) { hold = false; await new Promise<void>(resolve => { release = resolve; }); }
    return ok(data);
  }
  if (path === '/admin/v2/service-anomalies' && method === 'get') return ok({ items: [], total: 0 });
  if (path === '/admin/v2/service-anomalies/sync' && method === 'post') return ok({ detected: 0, created: 0, updated: 0, reopened: 0 });
  if (path === '/admin/exceptions' && method === 'get') {
    if (config.params.status !== 'unresolved') throw Error('Unresolved status required');
    return ok({ items: [{ id: 1, status, exception_type: 'missing_order', title: 'INTERNAL-STATE', due_at: null, assigned_to: null }] });
  }
  if (path === '/admin/exceptions/1/acknowledge' && method === 'post') {
    stats.ack++;
    await new Promise(resolve => setTimeout(resolve, 100));
    if (failAck) { failAck = false; return fail(); }
    status = 'acknowledged'; return ok({ id: 1, status });
  }
  if (path === '/technician/service-history' && method === 'get') {
    stats.filter = config.params.record_status;
    const offset = (Number(config.params.page) - 1) * 20;
    const items = Array.from({ length: Math.max(0, Math.min(20, stats.pending - offset)) }, (_, index) => ({
      ...service, occupancy_id: offset + index + 1, record_task: { ...service.record_task, selection_session_id: 'synthetic-closeout-' + (offset + index + 1) },
    }));
    return ok({ items, total: stats.pending, unassigned_legacy_count: 0 });
  }
  if (path === '/technician/service-record-options' && method === 'get') return ok({ taxonomy_version: 'service_handoff_v1', groups: { body_region: [], session_change: [] } });
  if (path === '/admin/v2/customer-profile-records' && method === 'post') {
    stats.saves++;
    if (failSave) { failSave = false; return fail(); }
    const body = JSON.parse(config.data);
    if (body.user_id !== 1001 || !/^synthetic-closeout-\d+$/.test(body.selection_session_id) || body.customer_confirmed !== false || body.profile.recording_outcome !== 'no_additional_notes') throw Error('Incorrect save payload');
    stats.pending--; return ok({ id: 44 });
  }
  stats.unexpected++; throw Error('Non-whitelisted fixture request');
};
function Fixture() {
  const [active, setActive] = useState(true);
  const [opened, setOpened] = useState('');
  return <ConfigProvider><App><main style={{ maxWidth: 430, margin: '0 auto', padding: 16 }}>
    <aside><h1>合成待办验收</h1><p>不连接生产</p>
      <button onClick={() => { stats.pending = 0; window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true })); }}>模拟返回并已补填</button>
      <button onClick={() => { clearStaffSession(); setActive(false); release?.(); }}>切换身份并释放旧响应</button>
      <p role="status">{opened}</p>
    </aside>
    {!active ? <p>身份已切换</p> : mode.startsWith('history') || mode === 'save-error'
      ? <TechnicianServiceHistoryPage />
      : <ManagerTasksView onOpenOrders={stale => setOpened(stale ? '超时服务单' : '全部服务单')} />}
  </main></App></ConfigProvider>;
}
createRoot(document.getElementById('root')!).render(<Fixture />);

import React from 'react';
import { createRoot } from 'react-dom/client';
import { App, ConfigProvider } from 'antd';
import { AxiosError } from 'axios';
import { client } from '../src/api';
import { writeStaffSession } from '../src/staffSession';
import ManagerStorePage from '../src/technician/ManagerStorePage';
import '../src/technician/technician-mobile.css';

writeStaffSession(localStorage, {token: 'synthetic-manager-only', staff: {id: 1, name: '合成店长', role: 'manager', store_id: 1}, authMethod: 'wecom'});
const mode = new URLSearchParams(location.search).get('mode');
const stats = {calls: [] as string[], saves: 0, unexpected: 0, listParams: [] as any[]};
(window as any).reviewStats = stats;
let failSave = mode === 'save-failure';
const base = {id: 7, selection_session_id: null, rating: 2, tags: [], follow_up_status: 'open', follow_up_note: '', followed_up_at: null, created_at: '2026-10-26T10:00:00+08:00', customer_phone: null};
const rows = [
  {...base, feedback_type: 'visit_feedback', note: '合成扫码反馈：请保持安静'},
  {...base, feedback_type: 'service_review', note: '合成服务评价：力度需再确认', selection_session_id: 'synthetic-service'},
];
client.defaults.adapter = async config => {
  const path = config.url || '', method = config.method;
  stats.calls.push(`${method} ${path}`);
  const ok = (data: unknown) => ({data, status: 200, statusText: 'OK', headers: {}, config});
  if (path === '/admin/v2/manager/workbench') return ok({summary: {today_orders: 0, waiting_service: 0, in_service: 0, completed_today: 0, attention: 2}, attention: [], record_follow_up: {pending_count: 0, window_days: 30, technicians: []}});
  if (path === '/admin/v2/selection-sessions') return ok({items: [], total: 0, page: 1, page_size: 20});
  if (path === '/admin/v2/feedback' && method === 'get') {
    stats.listParams.push(config.params);
    if (config.params?.feedback_type) throw Error('Both review sources are required');
    return ok({items: rows.map(row => ({...row})), total: 2, page: 1, page_size: 50});
  }
  const match = path.match(/^\/admin\/v2\/feedback\/(service_review|visit_feedback)\/7$/);
  if (match) {
    const row = rows.find(item => item.feedback_type === match[1])!;
    if (mode === 'forbidden' && method === 'get') throw new AxiosError('Synthetic unavailable review', 'ERR_BAD_REQUEST', config, undefined, {...ok({detail: '评价不存在'}), status: 404});
    if (method === 'patch') {
      stats.saves++;
      await new Promise(resolve => setTimeout(resolve, 150));
      if (failSave) {failSave = false; throw new AxiosError('Synthetic save failure', 'ERR_NETWORK', config);}
      Object.assign(row, JSON.parse(config.data));
    }
    return ok({...row});
  }
  if (path === '/admin/v2/service-anomalies/sync') return ok({detected: 0});
  if (path === '/admin/exceptions' || path === '/admin/v2/manager/unassigned-services') return ok({items: [], total: 0});
  stats.unexpected++; throw Error('Unexpected isolated request');
};
createRoot(document.getElementById('root')!).render(<ConfigProvider><App><main style={{maxWidth: 430, margin:'0 auto'}}><aside style={{padding:12, background:'#eef8f3'}}>合成数据 · 评价闭环验收 · 不连接生产</aside><ManagerStorePage /></main></App></ConfigProvider>);

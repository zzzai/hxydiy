import React, { useState } from 'react';
import ReactDOM from 'react-dom/client';
import { App, ConfigProvider } from 'antd';
import { BrowserRouter } from 'react-router-dom';
import { client } from '../src/api';
import { writeStaffSession } from '../src/staffSession';
import ManagerP0Page from '../src/technician/ManagerP0Page';
import { createCouponPoster } from '../src/technician/couponPoster';
import '../src/technician/technician-mobile.css';

const stats = { linkRequests: 0, unexpected: 0 };
Object.assign(window, { posterTest: stats });
const manager = { id: 99002, role: 'manager', technician_id: null, store_id: 2, name: '预览店长', store_name: '荷小悦-草本泡脚（华富世家店）' };
writeStaffSession(localStorage, { token: 'synthetic-poster-manager', staff: manager, authMethod: 'password' });
client.defaults.adapter = async config => {
  const path = config.url;
  const ok = (data: unknown) => ({ data, status: 200, statusText: 'OK', headers: {}, config });
  if (config.method === 'get' && path === '/admin/v2/manager/daily') return ok({
    business_date: '2026-11-12', status: 'draft', areas: [], meetings: [],
    completion: { areas_done: 0, areas_total: 5, has_meeting: false, submitted: false },
  });
  if (config.method === 'get' && path === '/admin/v2/manager/daily/team') return ok({ summary: { staff_count: 0, on_track: 0, overdue: 0 }, technicians: [] });
  if (config.method === 'get' && path === '/admin/v2/manager/workbench') return ok({
    store_id: 2, summary: { today_orders: 0, in_service: 0, pending_checkout: 0, attention: 0 }, attention: [],
    record_follow_up: { window_days: 30, pending_count: 0, technicians: [] },
  });
  if (config.method === 'post' && path === '/admin/v2/manager/coupons/half-price/poster-link') {
    stats.linkRequests++;
    return ok({ code: 'synthetic-claim-code', issued: 0, remaining: 100, limit: 100 });
  }
  stats.unexpected++;
  throw new Error('Preview rejected unexpected API request: ' + path);
};

function PosterPreview() {
  const [image, setImage] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const generate = async () => {
    setBusy(true); setError('');
    try {
      const response = await fetch('/preview-claim.json');
      if (!response.ok) throw new Error('预览领券链接未配置');
      const { link, store_name } = await response.json();
      setImage(await createCouponPoster(link, store_name));
    } catch (failure) { setError((failure as Error).message); }
    finally { setBusy(false); }
  };
  React.useEffect(() => { void generate(); }, []);
  return <main style={{ maxWidth: 760, margin: '24px auto', padding: '0 20px 40px', fontFamily: 'sans-serif', color: '#145545' }}>
    <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
      <div><strong>荷小悦 · 营销海报</strong><p style={{ fontSize: 13, color: '#65786b' }}>华富世家店 · 完整预览</p></div>
      <a download="荷小悦-华富世家店-半价券.png" href={image || undefined} style={{ color: '#145545' }}>保存原图</a>
    </header>
    {busy && <p role="status">正在生成海报…</p>}
    {error && <p role="alert">{error}</p>}
    {image && <img id="poster" src={image} alt="荷小悦华富世家店半价券海报" style={{ width: '100%', height: 'auto', display: 'block', boxShadow: '0 8px 36px #173a2414' }} />}
    <p style={{ fontSize: 12, color: '#65786b' }}>隔离预览，尚未发布。二维码使用已核验的线上领券链接；扫码会进入真实领券活动。</p>
    <button disabled={busy} onClick={() => void generate()}>重新生成海报</button>
  </main>;
}
ReactDOM.createRoot(document.getElementById('root')!).render(
  <ConfigProvider theme={{ token: { colorPrimary: '#145545' } }}><App>
    {location.pathname.startsWith('/technician/') ? <BrowserRouter basename="/technician"><div className="technician-mobile-app"><main className="technician-mobile-content"><ManagerP0Page /></main></div></BrowserRouter> : <PosterPreview />}
  </App></ConfigProvider>,
);

import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { App, ConfigProvider } from 'antd';
import PosterCouponClaimPage from '../../diy-web/src/components/PosterCouponClaimPage';
import ManagerCouponRedeemView from '../src/technician/ManagerCouponRedeemView';
import { client } from '../src/api';
import { clearCustomerAuth, writeCustomerAuth } from '../../diy-web/src/customerAuth';
import '../src/technician/manager-mobile.css';
import '../src/technician/manager-p0.css';

const key = 'hxy_isolated_poster_demo_v1';
type Demo = { owner: string | null; used: boolean; claims: number; redeems: number };
const read = (): Demo => JSON.parse(localStorage.getItem(key) || '{"owner":null,"used":false,"claims":0,"redeems":0}');
const save = (value: Demo) => localStorage.setItem(key, JSON.stringify(value));
const authFor = (phone: string) => ({
  token: 'preview.' + btoa(JSON.stringify({ phone, exp: Math.floor(Date.now() / 1000) + 3600 })) + '.synthetic',
  user: { id: phone.endsWith('000') ? 1 : 2, openid: 'synthetic', phone, nickname: '演示顾客', is_member: false, member_type: null, balance_cents: 0 },
});
const coupon = () => ({ coupon_id: 1, name: '半价券（全单5折）', percent_off: 50, expire_at: '2027-01-11T00:00:00+08:00', status: read().used ? 'used' : 'unused' });
const reply = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
const failure = (code: string, message: string, status = 409) => reply({ detail: { code, message } }, status);
const nativeFetch = window.fetch.bind(window);
Object.assign(window, { posterFlowTest: { read } });
window.fetch = async (input, init = {}) => {
  const path = String(input);
  if (!path.startsWith('/api/')) return nativeFetch(input, init);
  const body = JSON.parse(String(init.body || '{}'));
  const headers = new Headers(init.headers);
  let phone = '';
  try { phone = JSON.parse(atob((headers.get('Authorization') || '').split('.')[1])).phone; } catch { /* Anonymous preview. */ }
  const state = read();
  if (path.endsWith('/auth/h5/send-code')) return reply({ sent: true, expires_in_seconds: 300 });
  if (path.endsWith('/auth/h5/login')) return body.code === '123456' ? reply(authFor(body.phone)) : failure('CODE_INVALID', '演示验证码为 123456', 400);
  if (path.endsWith('/coupons/poster-status')) return reply(!state.owner ? { state: 'available', validity_days: 60 } : state.owner === phone ? { state: 'owned', coupon: coupon() } : { state: 'claimed' });
  if (path.endsWith('/coupons/claim-half-price')) {
    if (!phone) return failure('LOGIN_REQUIRED', '请登录', 401);
    if (state.owner && state.owner !== phone) return failure('POSTER_ALREADY_CLAIMED', '这张券已被领取');
    if (!state.owner) save({ ...state, owner: phone, claims: state.claims + 1 });
    return reply(coupon());
  }
  if (path.endsWith('/coupons/1/redeem-token')) {
    if (state.owner !== phone) return failure('COUPON_NOT_FOUND', '券不存在', 404);
    if (state.used) return failure('COUPON_ALREADY_USED', '该券已核销');
    return reply({ coupon_id: 1, token: 'r.synthetic-poster-owner-code', expires_at: new Date(Date.now() + 300000).toISOString() });
  }
  throw new Error('Isolated preview rejected API: ' + path);
};
client.defaults.adapter = async config => {
  const state = read();
  const body = JSON.parse(String(config.data || '{}'));
  const ok = (data: unknown) => ({ data, status: 200, statusText: 'OK', headers: {}, config });
  if (!state.owner || body.token !== 'r.synthetic-poster-owner-code') throw { response: { data: { detail: { message: '请先在顾客甲页面领取券，再演示扫码。' } } } };
  if (state.used) throw { response: { data: { detail: { message: '该券已核销' } } } };
  if (config.url === '/admin/v2/manager/coupons/validate') return ok({ ...coupon(), customer_name: '演示顾客', phone_masked: state.owner.slice(0, 3) + '****' + state.owner.slice(-4), requires_holder_confirmation: true });
  if (config.url === '/admin/v2/manager/coupons/redeem') {
    if (body.holder_present !== true) throw new Error('Holder confirmation required');
    save({ ...state, used: true, redeems: state.redeems + 1 });
    return ok({ ...coupon(), customer_name: '演示顾客' });
  }
  throw new Error('Isolated preview rejected manager API');
};
function Demo() {
  const [view, setView] = useState('guest');
  const [revision, setRevision] = useState(0);
  const choose = (next: string) => {
    if (next === 'guest') clearCustomerAuth();
    if (next === 'owner') writeCustomerAuth(authFor('13800138000'));
    if (next === 'other') writeCustomerAuth(authFor('13900139000'));
    setView(next); setRevision(value => value + 1);
  };
  return <ConfigProvider theme={{ token: { colorPrimary: '#145545' } }}><App>
    <aside style={{ maxWidth: 480, margin: 'auto', padding: '16px 18px', color: '#145545', background: '#f3f8f4', font: '13px/1.6 sans-serif' }}>
      <strong>隔离预览 · 合成顾客和券</strong><p>不会发送短信或发放真实券。顾客甲：13800138000；验证码：123456。</p>
      <nav style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>{[['guest','未登录扫码'],['owner','顾客甲'],['other','顾客乙'],['manager','店长扫码核销']].map(([id,label]) => <button key={id} onClick={() => choose(id)}>{label}</button>)}<button onClick={() => { localStorage.removeItem(key); choose('guest'); }}>重置演示</button></nav>
    </aside>
    {view === 'manager' ? <div style={{ maxWidth: 440, margin: 'auto', padding: 20 }}><ManagerCouponRedeemView key={revision} initialToken="r.synthetic-poster-owner-code" /></div> : <PosterCouponClaimPage key={revision} code="p.preview-single-claim" storeId={2} />}
  </App></ConfigProvider>;
}
createRoot(document.getElementById('root')!).render(<Demo />);

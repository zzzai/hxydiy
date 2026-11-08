import { useEffect, useRef, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';

import { claimHalfPriceCoupon, getCouponRedeemToken, getMyCoupons, loginByPhone, sendPhoneCode, type MyCoupon } from '../api';
import { isValidPhone, normalizePhone, readCustomerAuth, writeCustomerAuth, type CustomerAuth } from '../customerAuth';
import './coupon-claim.css';

type ClaimedCoupon = { id: number; name: string; percent_off: number; expire_at: string };

export default function CouponClaimPage() {
  const params = new URLSearchParams(window.location.search);
  const token = params.get('token') || '';
  const storeId = Number(params.get('store') || 1);
  const [auth, setAuth] = useState<CustomerAuth | null>(() => readCustomerAuth());
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [seconds, setSeconds] = useState(0);
  const [sending, setSending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [coupon, setCoupon] = useState<ClaimedCoupon | null>(null);
  const [qrToken, setQrToken] = useState('');
  const [error, setError] = useState('');
  const claimed = useRef(false);

  useEffect(() => {
    if (seconds <= 0) return;
    const timer = window.setInterval(() => setSeconds((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [seconds]);

  const issueQr = async (couponId: number, authToken: string) => {
    const qr = await getCouponRedeemToken(couponId, authToken);
    setQrToken(qr.token);
  };

  useEffect(() => {
    if (!auth?.token || !token || claimed.current) return;
    claimed.current = true;
    setBusy(true);
    setError('');
    void claimHalfPriceCoupon(token, auth.token).then(async (result) => {
      setCoupon({ id: result.coupon_id, name: result.name, percent_off: result.percent_off, expire_at: result.expire_at });
      await issueQr(result.coupon_id, auth.token);
    }).catch(async (failure: unknown) => {
      const detail = (failure as { response?: { data?: { detail?: { code?: string; message?: string } } } })?.response?.data?.detail;
      if (detail?.code === 'COUPON_ALREADY_HELD') {
        try {
          const coupons: MyCoupon[] = await getMyCoupons(auth.token);
          const existing = coupons.find((item) => item.coupon_type === 'percent' && item.percent_off === 50 && item.status === 'unused');
          if (existing) {
            setCoupon({ id: existing.id, name: existing.name, percent_off: existing.percent_off, expire_at: existing.expire_at || '' });
            await issueQr(existing.id, auth.token);
            return;
          }
        } catch { /* fall through */ }
      }
      setError(detail?.message || '领取失败，请联系店长');
    }).finally(() => setBusy(false));
  }, [auth?.token, token]);

  const sendCode = async () => {
    const value = normalizePhone(phone);
    if (!isValidPhone(value)) { setError('请输入正确手机号'); return; }
    setSending(true); setError('');
    try { await sendPhoneCode(value); setSeconds(60); }
    catch (failure) { setError(failure instanceof Error ? failure.message : '验证码发送失败'); }
    finally { setSending(false); }
  };

  const login = async () => {
    const value = normalizePhone(phone);
    if (!isValidPhone(value) || code.length !== 6) { setError('请输入手机号和 6 位验证码'); return; }
    setBusy(true); setError('');
    try {
      const result = await loginByPhone(value, code);
      writeCustomerAuth(result);
      setAuth(result);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : '登录失败');
    } finally { setBusy(false); }
  };

  const menuUrl = `/?store=${storeId}&view=menu`;
  const couponUrl = `/?store=${storeId}&view=return&coupon=1`;

  return <main className="coupon-claim-page">
    <section className="coupon-claim-card">
      <header><span>荷小悦</span><h1>半价券</h1><p>全单 5 折 · 领取后 60 天有效</p></header>
      {!token ? <p className="coupon-claim-error">链接无效，请让店长重新发送。</p>
        : !auth ? <>
          <p className="coupon-claim-hint">登录后领取，也能在「我的券」看到，并查看项目菜单。</p>
          <label>手机号<input inputMode="numeric" maxLength={11} value={phone} placeholder="请输入手机号" onChange={(event) => setPhone(event.target.value.replace(/\D/g, ''))} /></label>
          <div className="coupon-claim-code"><input inputMode="numeric" maxLength={6} value={code} placeholder="验证码" onChange={(event) => setCode(event.target.value.replace(/\D/g, ''))} /><button type="button" disabled={sending || seconds > 0} onClick={() => void sendCode()}>{seconds > 0 ? `${seconds}s` : sending ? '发送中' : '获取验证码'}</button></div>
          {error && <p className="coupon-claim-error">{error}</p>}
          <button type="button" className="coupon-claim-primary" disabled={busy} onClick={() => void login()}>登录并领取</button>
        </> : busy ? <p className="coupon-claim-hint">正在领取半价券…</p>
          : error ? <><p className="coupon-claim-error">{error}</p><a className="coupon-claim-link" href={couponUrl}>打开我的券</a></>
            : coupon ? <>
              <div className="coupon-claim-value"><strong>5折</strong><span>全单可用</span></div>
              {qrToken && <QRCodeSVG value={`${window.location.origin}/technician/store?coupon=${encodeURIComponent(qrToken)}`} size={220} />}
              <p className="coupon-claim-hint">请店长扫码核销</p>
              <p className="coupon-claim-meta">有效期至 {coupon.expire_at ? new Date(coupon.expire_at).toLocaleDateString('zh-CN') : '60 天后'}</p>
              <p className="coupon-claim-hint">登录后也能在「我的券」看到，还能查看项目菜单。</p>
              <div className="coupon-claim-actions"><a href={menuUrl}>看项目菜单</a><a href={couponUrl}>我的券</a></div>
            </> : null}
    </section>
  </main>;
}

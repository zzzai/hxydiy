import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, Clock3 } from 'lucide-react';
import { QRCodeSVG } from 'qrcode.react';

import {
  ApiError, bindGuestCoupon, claimHalfPriceCoupon, getCouponRedeemToken, getGuestCoupon, getGuestCouponRedeemToken,
  getMyCoupons, guestClaimCoupon, loginByPhone, sendPhoneCode, type GuestCoupon, type MyCoupon,
} from '../api';
import { GUEST_COUPON_KEY_PREFIX } from '../guestCoupon';
import { isValidPhone, normalizePhone, readCustomerAuth, writeCustomerAuth, type CustomerAuth } from '../customerAuth';
import './coupon-claim.css';

type CouponView = { id: number; name: string; percent_off: number; expire_at: string; status: string };

function couponFromGuest(value: GuestCoupon): CouponView {
  return { id: value.coupon_id, name: value.name, percent_off: value.percent_off, expire_at: value.expire_at || '', status: value.status };
}

function errorDetail(failure: unknown): { code?: string; message?: string } {
  if (failure instanceof ApiError) return { code: failure.code, message: failure.message };
  return (failure as { response?: { data?: { detail?: { code?: string; message?: string } } } })?.response?.data?.detail || {};
}

export default function CouponClaimPage() {
  const params = new URLSearchParams(window.location.search);
  const code = params.get('c') || params.get('token') || '';
  const storeId = Number(params.get('store') || 1);
  const [auth, setAuth] = useState<CustomerAuth | null>(() => readCustomerAuth());
  const [phone, setPhone] = useState('');
  const [smsCode, setSmsCode] = useState('');
  const [seconds, setSeconds] = useState(0);
  const [sending, setSending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [coupon, setCoupon] = useState<CouponView | null>(null);
  const [qrToken, setQrToken] = useState('');
  const [qrExpiresAt, setQrExpiresAt] = useState(0);
  const [qrRemaining, setQrRemaining] = useState(0);
  const [guestToken, setGuestToken] = useState('');
  const [error, setError] = useState('');
  const [guestReady, setGuestReady] = useState(false);
  const guestKey = code ? `${GUEST_COUPON_KEY_PREFIX}${code}` : '';
  const runKey = useRef('');

  useEffect(() => {
    if (seconds <= 0) return;
    const timer = window.setInterval(() => setSeconds((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [seconds]);

  const issueQr = async (couponId: number, authToken: string) => {
    const qr = await getCouponRedeemToken(couponId, authToken);
    setQrToken(qr.token);
    setQrExpiresAt(Date.parse(qr.expires_at) || Date.now() + 300_000);
  };

  const issueGuestQr = async (token: string) => {
    const qr = await getGuestCouponRedeemToken(token);
    setQrToken(qr.token);
    setQrExpiresAt(Date.parse(qr.expires_at) || Date.now() + 300_000);
  };

  useEffect(() => {
    const tick = () => setQrRemaining(qrExpiresAt ? Math.max(0, Math.ceil((qrExpiresAt - Date.now()) / 1000)) : 0);
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [qrExpiresAt]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible' && qrExpiresAt && Date.now() >= qrExpiresAt && coupon?.status === 'unused') {
        void (auth?.token ? issueQr(coupon.id, auth.token) : guestToken ? issueGuestQr(guestToken) : Promise.resolve());
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [auth?.token, coupon, guestToken, qrExpiresAt]);

  const showExisting = async (authToken: string) => {
    const coupons: MyCoupon[] = await getMyCoupons(authToken);
    const existing = coupons.find((item) => item.coupon_type === 'percent' && item.percent_off === 50 && item.status === 'unused')
      || coupons.find((item) => item.coupon_type === 'percent' && item.percent_off === 50);
    if (!existing) return false;
    setCoupon({ id: existing.id, name: existing.name, percent_off: existing.percent_off, expire_at: existing.expire_at || '', status: existing.status });
    if (existing.status === 'unused') await issueQr(existing.id, authToken);
    return true;
  };

  useEffect(() => {
    if (!code) return;
    const key = `${auth?.token || 'guest'}:${code}`;
    if (runKey.current === key) return;
    runKey.current = key;
    setError('');
    setBusy(true);
    const run = async () => {
      if (!auth?.token) {
        let guestToken = window.localStorage.getItem(guestKey) || '';
        if (guestToken) {
          try {
            const guest = await getGuestCoupon(guestToken);
            setGuestToken(guestToken);
            setCoupon(couponFromGuest(guest));
            if (guest.status === 'unused') await issueGuestQr(guestToken);
            setGuestReady(true);
            return;
          } catch {
            window.localStorage.removeItem(guestKey);
            guestToken = '';
          }
        }
        // Opening the link is only a preview. A coupon (and quota) is created
        // only when the customer explicitly claims it or logs in.
        setGuestReady(false);
        return;
      }

      const guestToken = window.localStorage.getItem(guestKey) || '';
      if (guestToken) {
        try {
          const bound = await bindGuestCoupon(guestToken, auth.token);
          window.localStorage.removeItem(guestKey);
          setCoupon({ id: bound.coupon_id, name: bound.name, percent_off: bound.percent_off, expire_at: bound.expire_at || '', status: bound.status });
          if (bound.status === 'unused') await issueQr(bound.coupon_id, auth.token);
          return;
        } catch (failure) {
          const detail = errorDetail(failure);
          if (detail.code === 'COUPON_ALREADY_BOUND') {
            window.localStorage.removeItem(guestKey);
          }
        }
      }
      try {
        const claimed = await claimHalfPriceCoupon(code, auth.token);
        setCoupon({ id: claimed.coupon_id, name: claimed.name, percent_off: claimed.percent_off, expire_at: claimed.expire_at, status: 'unused' });
        await issueQr(claimed.coupon_id, auth.token);
      } catch (failure) {
        const detail = errorDetail(failure);
        if (detail.code === 'COUPON_ALREADY_HELD') {
          if (await showExisting(auth.token)) return;
        }
        setError(detail.message || '领取失败，请联系店长');
      }
    };
    void run().catch((failure) => {
      const detail = errorDetail(failure);
      setError(detail.message || '领券失败，请稍后重试');
    }).finally(() => setBusy(false));
  }, [auth?.token, code, guestKey]);

  const claimGuest = async () => {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      let visitorId = window.localStorage.getItem('hxy_coupon_visitor') || '';
      if (!visitorId) {
        visitorId = window.crypto?.randomUUID?.() || `guest-${Date.now()}-${Math.random().toString(36).slice(2)}`;
        window.localStorage.setItem('hxy_coupon_visitor', visitorId);
      }
      const guest = await guestClaimCoupon(code, visitorId);
      window.localStorage.setItem(guestKey, guest.guest_token);
      setGuestToken(guest.guest_token);
      setCoupon(couponFromGuest(guest));
      if (guest.status === 'unused') await issueGuestQr(guest.guest_token);
      setGuestReady(true);
    } catch (failure) {
      const detail = errorDetail(failure);
      setError(detail.message || '领取失败，请稍后重试');
    } finally {
      setBusy(false);
    }
  };

  const sendCode = async () => {    const value = normalizePhone(phone);
    if (!isValidPhone(value)) { setError('请输入正确手机号'); return; }
    setSending(true); setError('');
    try { await sendPhoneCode(value); setSeconds(60); }
    catch (failure) { setError(failure instanceof Error ? failure.message : '验证码发送失败'); }
    finally { setSending(false); }
  };

  const login = async () => {
    const value = normalizePhone(phone);
    if (!isValidPhone(value) || smsCode.length !== 6) { setError('请输入手机号和 6 位验证码'); return; }
    setBusy(true); setError('');
    try {
      const result = await loginByPhone(value, smsCode);
      writeCustomerAuth(result);
      runKey.current = '';
      setAuth(result);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : '登录失败');
    } finally { setBusy(false); }
  };

  const menuUrl = `/?store=${storeId}&view=menu`;
  const couponUrl = `/?store=${storeId}&view=profile&coupon=1`;
  const usable = coupon?.status === 'unused';
  const terminal = Boolean(coupon && !usable);
  const used = coupon?.status === 'used';
  const statusTitle = used ? '这张券已核销' : coupon?.status === 'expired' ? '这张券已过期' : '这张券暂不可用';
  const statusDetail = used
    ? '门店已经完成核销，这张券不能再次使用。'
    : coupon?.status === 'expired'
      ? '已超过有效期，请让店长重新发券。'
      : '当前状态不可出示核销码，请联系门店确认。';
  const refreshQr = () => {
    if (!coupon) return;
    if (auth?.token) void issueQr(coupon.id, auth.token);
    else if (guestToken) void issueGuestQr(guestToken);
  };

  return <main className="coupon-claim-page">
    <section className="coupon-claim-card">
      <header><span>荷小悦</span><h1>半价券</h1><p>{terminal ? `全单 5 折 · ${used ? '已核销' : '已过期'}` : '全单 5 折 · 领取后 60 天有效'}</p></header>
      {!terminal ? <p className="coupon-claim-poster-copy">忙完一天，来泡个脚，给自己松一松。</p> : null}
      {!code ? <p className="coupon-claim-error">链接无效，请让店长重新发送。</p> : <>
        {busy && !coupon ? <p className="coupon-claim-hint">正在准备半价券…</p> : null}
        {error ? <><p className="coupon-claim-error">{error}</p><div className="coupon-claim-actions"><a href={menuUrl}>看项目菜单</a><a href={couponUrl}>我的券包</a></div></> : null}
        {coupon ? <>
          {usable
            ? <div className="coupon-claim-value"><strong>{coupon.percent_off / 10}折</strong><span>全单可用</span></div>
            : <section className={`coupon-claim-status ${coupon.status}`} role="status" aria-live="polite">
                {used ? <CheckCircle2 size={42} aria-hidden="true" /> : <Clock3 size={42} aria-hidden="true" />}
                <strong>{statusTitle}</strong>
                <p>{statusDetail}</p>
              </section>}
          {usable && qrToken && qrRemaining > 0 ? <QRCodeSVG value={`${window.location.origin}/technician/store?coupon=${encodeURIComponent(qrToken)}`} size={220} level="L" /> : null}
          {usable && qrToken && qrRemaining > 0 ? <p className="coupon-claim-hint">无需登录也能核销；请店长扫码 · 核销码 {Math.floor(qrRemaining / 60)}:{String(qrRemaining % 60).padStart(2, '0')} 内有效</p> : null}
          {usable && qrToken && qrRemaining > 0 ? <button type="button" className="coupon-claim-link" onClick={() => { void navigator.clipboard?.writeText(qrToken); }}>复制核销码</button> : null}
          {usable && qrToken && qrRemaining <= 0 ? <><p className="coupon-claim-meta">核销码已过期，请刷新后再给店长扫码。</p><button type="button" className="coupon-claim-primary" onClick={refreshQr}>刷新核销码</button></> : null}
          {usable && !qrToken ? <p className="coupon-claim-meta">正在生成核销码…</p> : null}
          {usable ? <p className="coupon-claim-meta">有效期至 {coupon.expire_at ? new Date(coupon.expire_at).toLocaleDateString('zh-CN') : '60 天后'}</p> : null}
          {usable ? <p className="coupon-claim-hint">登录后可保存到「券包」，也能查看项目菜单。</p> : null}
          {usable && !auth ? <p className="coupon-claim-hint">不登录也能看到券和核销码；登录后这张券会自动绑定到你的账户。</p> : null}
          <div className="coupon-claim-actions">
            <a className={terminal ? 'primary' : ''} href={menuUrl}>看项目菜单</a>
            <a href={couponUrl}>我的券包</a>
          </div>
        </> : null}
        {!auth && !coupon && !busy ? <div className="coupon-claim-preview"><div className="coupon-claim-value"><strong>5折</strong><span>全单可用</span></div><p className="coupon-claim-hint">先预览，不占用 100 张额度。领取后才生成券和核销码。</p><button type="button" className="coupon-claim-primary" disabled={busy} onClick={() => void claimGuest()}>领取并出示核销码</button></div> : null}
        {!auth && !terminal ? <>
          <div className="coupon-claim-divider"><span>或登录后自动领取</span></div>
          <label>手机号<input inputMode="numeric" maxLength={11} value={phone} placeholder="请输入手机号" onChange={(event) => setPhone(event.target.value.replace(/\D/g, ''))} /></label>
          <div className="coupon-claim-code"><input inputMode="numeric" maxLength={6} value={smsCode} placeholder="验证码" onChange={(event) => setSmsCode(event.target.value.replace(/\D/g, ''))} /><button type="button" disabled={sending || seconds > 0} onClick={() => void sendCode()}>{seconds > 0 ? `${seconds}s` : sending ? '发送中' : '获取验证码'}</button></div>
          <button type="button" className="coupon-claim-primary" disabled={busy} onClick={() => void login()}>登录并领取到券包</button>
          {!guestReady && !coupon && <p className="coupon-claim-hint">未登录打开只预览；点领取或登录后才占用一张。</p>}
        </> : null}
      </>}
    </section>
  </main>;
}

import { useEffect, useRef, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { ApiError, claimPosterCoupon, getCouponPosterStatus, getCouponRedeemToken, loginByPhone, sendPhoneCode, type PosterCouponStatus } from '../api';
import { clearCustomerAuth, isValidPhone, normalizePhone, readCustomerAuth, writeCustomerAuth } from '../customerAuth';
import './coupon-claim.css';

export default function PosterCouponClaimPage({ code, storeId }: { code: string; storeId: number }) {
  const [auth, setAuth] = useState(readCustomerAuth);
  const [status, setStatus] = useState<PosterCouponStatus | null>(null);
  const [phone, setPhone] = useState('');
  const [smsCode, setSmsCode] = useState('');
  const [seconds, setSeconds] = useState(0);
  const [sending, setSending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState('');
  const [showLogin, setShowLogin] = useState(false);
  const [qr, setQr] = useState<{ token: string; expires_at: string } | null>(null);
  const [now, setNow] = useState(Date.now());
  const actionPending = useRef(false);
  const statusVersion = useRef(0);
  const coupon = status?.state === 'owned' ? status.coupon : null;
  const loggedIn = Boolean(auth?.token && auth.user.phone);
  const unavailable = status?.state === 'unavailable';
  const claimed = status?.state === 'claimed';

  const fail = (failure: unknown) => {
    if (failure instanceof ApiError && failure.status === 401) {
      clearCustomerAuth(); setAuth(null); setShowLogin(true); setQr(null); setStatus(null);
      setError('登录已失效，请重新验证手机号。');
    } else {
      setError(failure instanceof Error ? failure.message : '暂时未能完成，请稍后重试');
    }
  };
  const refresh = async () => {
    const version = ++statusVersion.current;
    setChecking(true);
    try {
      const result = await getCouponPosterStatus(code, auth?.token);
      if (version === statusVersion.current) {
        setStatus(result);
        if (result.state !== 'owned' || result.coupon.status !== 'unused') setQr(null);
      }
    } catch (failure) { if (version === statusVersion.current) fail(failure); }
    finally { if (version === statusVersion.current) setChecking(false); }
  };
  useEffect(() => {
    void refresh();
    const onVisible = () => { if (document.visibilityState === 'visible' && !actionPending.current) void refresh(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => { statusVersion.current++; document.removeEventListener('visibilitychange', onVisible); };
  }, [code, auth?.token]);
  useEffect(() => {
    const timer = window.setInterval(() => { setNow(Date.now()); setSeconds(value => Math.max(0, value - 1)); }, 1000);
    return () => window.clearInterval(timer);
  }, []);
  const sendCode = async () => {
    if (sending || seconds > 0) return;
    if (!isValidPhone(phone)) { setError('请输入正确的手机号'); return; }
    setSending(true); setError('');
    try { await sendPhoneCode(normalizePhone(phone)); setSeconds(60); }
    catch (failure) { fail(failure); }
    finally { setSending(false); }
  };
  const claim = async () => {
    if (actionPending.current) return;
    actionPending.current = true;
    setBusy(true); setError('');
    try {
      let current = auth;
      if (!loggedIn) {
        if (!isValidPhone(phone) || smsCode.length !== 6) { setError('请输入手机号和 6 位验证码'); return; }
        current = await loginByPhone(normalizePhone(phone), smsCode);
        writeCustomerAuth(current); setAuth(current);
      }
      const owned = await claimPosterCoupon(code, current!.token);
      statusVersion.current++;
      setStatus({ state: 'owned', coupon: owned }); setChecking(false); setQr(null);
    } catch (failure) {
      if (failure instanceof ApiError && failure.code === 'POSTER_ALREADY_CLAIMED') {
        statusVersion.current++;
        setStatus({ state: 'claimed' }); setChecking(false); setQr(null);
      } else fail(failure);
    } finally { actionPending.current = false; setBusy(false); }
  };
  const showRedeemCode = async () => {
    if (!coupon || !auth || actionPending.current) return;
    actionPending.current = true; setBusy(true); setError('');
    try {
      const result = await getCouponRedeemToken(coupon.coupon_id, auth.token);
      setQr(result); setNow(Date.now());
    } catch (failure) { setQr(null); fail(failure); await refresh(); }
    finally { actionPending.current = false; setBusy(false); }
  };
  const qrRemaining = qr ? Math.max(0, Math.ceil((Date.parse(qr.expires_at) - now) / 1000)) : 0;
  const loginVisible = !loggedIn && !coupon && !unavailable && (!claimed || showLogin);
  return <main className="coupon-claim-page poster-claim-page">
    <section className="coupon-claim-card">
      <header><span>荷小悦 · 家门口的养生小馆</span><h1>留一份放松给自己</h1><p>足疗、SPA主项5折 · 领取后60天有效</p></header>
      {!coupon && !claimed && !unavailable && <div className="coupon-claim-value"><strong>5折</strong><span>按门店价5折，不叠加会员价</span></div>}
      <p className="coupon-claim-hint">仅限足疗、SPA主项；小项、加项、痛症调理及套盒不参与，不叠加其他优惠。登录领取后可在菜单查看持券价。</p>
      {checking && !status && <p role="status">正在查看券状态…</p>}
      {claimed && <section className="coupon-claim-status" role="status"><strong>这张券已被领取</strong><p>这张海报仅对应一张券，领取后绑定领取人的账户，不能转给他人使用。</p></section>}
      {unavailable && <section className="coupon-claim-status" role="status"><strong>领券活动已结束</strong><p>可以查看门店正在提供的项目。</p></section>}
      {coupon && <section className={'coupon-claim-status ' + coupon.status} role="status">
        <strong>{coupon.status === 'unused' ? '已领取，已绑定本人' : coupon.status === 'used' ? '这张券已核销' : coupon.status === 'expired' ? '这张券已过期' : '这张券暂不可用'}</strong>
        <p>{coupon.status === 'unused' ? '到店后从本人账户出示核销码，请店长核对后使用。' : '原券记录保留，不能再次领取或使用。'}</p>
        {coupon.expire_at && <p>有效期至 {new Date(coupon.expire_at).toLocaleDateString('zh-CN')}</p>}
      </section>}
      {error && <p className="coupon-claim-error" role="alert">{error}</p>}
      {!checking && !status && <button type="button" className="coupon-claim-link" onClick={() => void refresh()}>重新加载</button>}
      {status?.state === 'available' && <p className="coupon-claim-hint">本张海报仅 1 张券，先领取先获得。登录后领取并绑定本人，不能转赠；打开页面不会占用名额。</p>}
      {loginVisible && <>
        <label>手机号<input type="tel" autoComplete="tel" inputMode="numeric" maxLength={11} value={phone} placeholder="请输入本人手机号" onChange={event => setPhone(normalizePhone(event.target.value))} /></label>
        <div className="coupon-claim-code"><input aria-label="短信验证码" autoComplete="one-time-code" inputMode="numeric" maxLength={6} value={smsCode} placeholder="6 位短信验证码" onChange={event => setSmsCode(event.target.value.replace(/\D/g, ''))} /><button type="button" disabled={sending || seconds > 0 || busy} onClick={() => void sendCode()}>{seconds > 0 ? seconds + 's' : sending ? '发送中' : '获取验证码'}</button></div>
        <button type="button" className="coupon-claim-primary" disabled={busy || checking || !status} onClick={() => void claim()}>{busy ? '正在处理…' : claimed ? '登录查看本人券' : '登录并领取'}</button>
      </>}
      {claimed && !loggedIn && !showLogin && <button type="button" className="coupon-claim-link" onClick={() => setShowLogin(true)}>已领取？登录查看本人券</button>}
      {status?.state === 'available' && loggedIn && <>
        <p className="coupon-claim-hint">领取至 {auth!.user.phone.replace(/(\d{3})\d{4}(\d{4})/, '$1****$2')} 的账户</p>
        <button type="button" className="coupon-claim-primary" disabled={busy || checking} onClick={() => void claim()}>{busy ? '领取中…' : '领取并绑定本人'}</button>
      </>}
      {coupon?.status === 'unused' && <>
        {qr && qrRemaining > 0 && <><QRCodeSVG value={window.location.origin + '/technician/store?coupon=' + encodeURIComponent(qr.token)} size={220} level="M" marginSize={4} /><p className="coupon-claim-hint">请本人现场出示 · 核销码 {Math.floor(qrRemaining / 60)}:{String(qrRemaining % 60).padStart(2, '0')} 内有效</p></>}
        {(!qr || qrRemaining === 0) && <button type="button" className="coupon-claim-primary" disabled={busy} onClick={() => void showRedeemCode()}>{busy ? '正在生成…' : qr ? '刷新核销码' : '到店出示核销码'}</button>}
      </>}
      <div className="coupon-claim-actions"><a href={'/?store=' + storeId + '&view=menu'}>看项目菜单</a><a href={'/?store=' + storeId + '&view=profile&coupon=1'}>我的券包</a></div>
    </section>
  </main>;
}

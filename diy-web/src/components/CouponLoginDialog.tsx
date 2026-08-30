import { ArrowLeft, CheckCircle2, TicketPercent } from 'lucide-react';
import { useEffect, useState } from 'react';

import { ApiError, claimCoupon, loginByPhone, sendPhoneCode, type CouponTemplate } from '../api';
import { isValidPhone, normalizePhone, writeCustomerAuth, type CustomerAuth } from '../customerAuth';
import { formatCouponReminder } from '../domain';
import { maskedPhone } from '../profile';

type Props = {
  open: boolean;
  coupon: CouponTemplate | null;
  auth: CustomerAuth | null;
  selectionSessionId?: string;
  selectionToken?: string;
  onClose: () => void;
  onSuccess: (auth: CustomerAuth, message: string) => void;
};

export default function CouponLoginDialog({ open, coupon, auth, selectionSessionId, selectionToken, onClose, onSuccess }: Props) {
  const [phone, setPhone] = useState(auth?.user.phone || '');
  const [code, setCode] = useState('');
  const [seconds, setSeconds] = useState(0);
  const [debugCode, setDebugCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    setPhone(auth?.user.phone || '');
    setCode('');
    setDebugCode('');
    setError('');
  }, [open, auth?.user.phone]);

  useEffect(() => {
    if (seconds <= 0) return undefined;
    const timer = window.setTimeout(() => setSeconds((value) => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [seconds]);

  if (!open) return null;

  const finishClaim = async (nextAuth: CustomerAuth) => {
    if (!coupon) throw new Error('当前暂无可领取优惠券');
    const result = await claimCoupon(coupon.id, nextAuth.token);
    onSuccess(nextAuth, `${result.name}已领取`);
  };

  const send = async () => {
    if (!isValidPhone(phone)) return setError('请输入正确的手机号');
    setBusy(true); setError('');
    try {
      const result = await sendPhoneCode(phone);
      setSeconds(60);
      setDebugCode(result.debug_code || '');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '验证码发送失败');
    } finally { setBusy(false); }
  };

  const confirm = async () => {
    if (auth) {
      setBusy(true); setError('');
      try { await finishClaim(auth); } catch (reason) { setError(reason instanceof Error ? reason.message : '领取失败'); } finally { setBusy(false); }
      return;
    }
    if (!isValidPhone(phone) || code.length !== 6) return setError('请输入手机号和 6 位验证码');
    setBusy(true); setError('');
    try {
      const nextAuth = await loginByPhone(phone, code, selectionSessionId, selectionToken);
      writeCustomerAuth(nextAuth);
      await finishClaim(nextAuth);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : reason instanceof Error ? reason.message : '登录失败');
    } finally { setBusy(false); }
  };

  return (
    <div className="coupon-login-page" role="dialog" aria-modal="true" aria-labelledby="coupon-login-title">
      <header><button type="button" aria-label="返回" onClick={onClose}><ArrowLeft size={22} /></button><strong>领取优惠券</strong><span /></header>
      <main>
        <section className="coupon-login-ticket">
          <TicketPercent size={28} />
          <div><small>荷小悦到店礼遇</small><h1 id="coupon-login-title">{coupon ? formatCouponReminder(coupon) : '登录领取优惠券'}</h1><p>领取后保存到当前账号，优惠以门店最终结算为准。</p></div>
        </section>
        {auth ? (
          <section className="coupon-account-ready"><CheckCircle2 size={24} /><div><strong>{maskedPhone(auth.user.phone)}</strong><p>已登录，可直接领取到当前账号。</p></div></section>
        ) : (
          <section className="coupon-login-form">
            <label><span>手机号</span><input value={phone} inputMode="tel" placeholder="请输入手机号" onChange={(event) => setPhone(normalizePhone(event.target.value))} /></label>
            <label><span>验证码</span><div><input value={code} inputMode="numeric" maxLength={6} placeholder="6 位验证码" onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))} /><button type="button" disabled={busy || seconds > 0} onClick={send}>{seconds > 0 ? `${seconds}s` : '获取验证码'}</button></div></label>
            {debugCode && <p className="coupon-debug-code">本地测试验证码：{debugCode}</p>}
          </section>
        )}
        {error && <p className="coupon-login-error">{error}</p>}
      </main>
          <footer><button type="button" disabled={busy || !coupon} onClick={confirm}>{busy ? '处理中' : auth ? '立即领取' : '登录并领取'}</button><p>优惠符合条件后预计自动抵扣，最终以门店完成服务后的结算清单为准。</p></footer>
    </div>
  );
}

import { ArrowLeft, ShieldCheck, UserRoundCheck } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { ApiError, loginByPhone, sendPhoneCode } from '../api';
import { isValidPhone, normalizePhone, writeCustomerAuth, type CustomerAuth } from '../customerAuth';
import { customerLoginCopy } from '../customerCopy';

export default function RecordLoginDialog({ open, selectionSessionId, selectionToken, onClose, onSuccess, purpose = 'record', notice = '' }: {
  open: boolean;
  selectionSessionId: string;
  selectionToken: string;
  onClose: () => void;
  onSuccess: (auth: CustomerAuth) => void;
  purpose?: 'record' | 'report';
  notice?: string;
}) {
  const copy = purpose === 'report' ? { title: '我的检测报告', detail: '用检测时的手机号登录，查看最近一次报告。', action: '登录并查看报告' } : customerLoginCopy('record');
  const active = useRef(false);
  const submitting = useRef(false);
  useEffect(() => { active.current = open; return () => { active.current = false; }; }, [open]);
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [seconds, setSeconds] = useState(0);
  const [debugCode, setDebugCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    setCode('');
    setDebugCode('');
    setError('');
  }, [open]);

  useEffect(() => {
    if (seconds <= 0) return undefined;
    const timer = window.setTimeout(() => setSeconds((value) => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [seconds]);

  if (!open) return null;

  const send = async () => {
    if (!isValidPhone(phone)) return setError('请输入正确的手机号');
    setBusy(true);
    setError('');
    try {
      const result = await sendPhoneCode(phone);
      setSeconds(60);
      setDebugCode(result.debug_code || '');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '验证码发送失败');
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    if (purpose === 'report' && submitting.current) return;
    if (!isValidPhone(phone) || code.length !== 6) return setError('请输入手机号和 6 位验证码');
    submitting.current = true;
    setBusy(true);
    setError('');
    try {
      const auth = await loginByPhone(phone, code, selectionSessionId, selectionToken);
      if (purpose === 'report' && !active.current) return;
      writeCustomerAuth(auth);
      onSuccess(auth);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : reason instanceof Error ? reason.message : '登录失败');
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  };

  return (
    <div className={`coupon-login-page${purpose === 'report' ? ' report-entry-login' : ''}`} role="dialog" aria-modal="true" aria-labelledby={purpose === 'report' ? undefined : 'record-login-title'} aria-label={purpose === 'report' ? '查看我的检测报告' : undefined}>
      <header><button type="button" aria-label="返回" onClick={onClose}><ArrowLeft size={22} /></button><strong>{purpose === 'report' ? '' : '查看服务记录'}</strong><span /></header>
      <main>
        <section className="coupon-login-ticket">
          <UserRoundCheck size={28} />
          <div>{purpose !== 'report' && <small>荷小悦到店服务</small>}<h1 id="record-login-title">{copy.title}</h1><p>{copy.detail}</p></div>
        </section>
        <section className="coupon-login-form">
          <label><span>手机号</span><input value={phone} inputMode="tel" placeholder="请输入手机号" onChange={(event) => setPhone(normalizePhone(event.target.value))} /></label>
          <label><span>验证码</span><div><input value={code} inputMode="numeric" maxLength={6} placeholder="6 位验证码" onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))} /><button type="button" disabled={busy || seconds > 0} onClick={send}>{seconds > 0 ? `${seconds}s` : '获取验证码'}</button></div></label>
          {debugCode && <p className="coupon-debug-code">本地测试验证码：{debugCode}</p>}
        </section>
        {purpose === 'report' && notice && <p className="coupon-login-error" role="alert">{notice}</p>}
        {error && <p className="coupon-login-error">{error}</p>}
      </main>
      <footer><button type="button" disabled={busy} onClick={confirm}>{busy ? '正在登录' : copy.action}</button>{purpose === 'report' ? <p>仅查看本人报告</p> : <p><ShieldCheck size={12} style={{ verticalAlign: '-2px' }} /> 仅用于识别您的到店服务记录。</p>}</footer>
    </div>
  );
}

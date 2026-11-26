import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Spin } from 'antd';
import { useNavigate } from 'react-router-dom';
import { technicianMobileHome } from './technicianMobile';
import { beginWecomEntry, clearStaffSession, completeWecomEntry, getSessionEpoch, hasManagerPendingDeepLink, wecomLoginPath } from '../wecomSession';

export default function TechnicianWecomGate({ complete = false }: { complete?: boolean }) {
  const navigate = useNavigate();
  const loginPath = useRef(wecomLoginPath()).current;
  const verifiedRole = useRef<'technician' | 'manager'>();
  const weekly = useRef<{ text: string; epoch: number }>();
  const [showWeekly, setShowWeekly] = useState(false);
  const pending = useRef<Promise<boolean | void>>();
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    pending.current ||= complete ? completeWecomEntry((role, summary) => {
      verifiedRole.current = role;
      if (summary) weekly.current = { text: summary, epoch: getSessionEpoch() };
    }) : beginWecomEntry();
    void pending.current.then((accepted) => {
      if (!active || !complete) return;
      if (accepted && verifiedRole.current) {
        if (weekly.current) { setShowWeekly(true); return; }
        const managerStaff = (() => {
          try { return JSON.parse(localStorage.getItem('hxy_admin_staff') || 'null') as { technician_id?: number | null } | null; }
          catch { return null; }
        })();
        const target = verifiedRole.current === 'manager'
          ? (hasManagerPendingDeepLink() ? '/store' : technicianMobileHome('manager', managerStaff?.technician_id))
          : '/today';
        navigate(target, { replace: true });
      }
      else setError('本次登录已失效，请重新进入企业微信工作台。');
    }).catch(() => {
      if (active) setError('企业微信身份验证未完成，请重试或使用账号登录。');
    });
    return () => { active = false; };
  }, [complete, navigate, attempt]);

  if (showWeekly && weekly.current?.epoch === getSessionEpoch()) {
    const [heading, ...stores] = weekly.current.text.split('\n\n');
    return <main className="inspection-weekly-report">
      <h1>{heading}</h1>
      {stores.map(section => {
        const [store, ...details] = section.split('\n');
        return <section key={store}><h2>{store}</h2>{details.map(line => <p key={line}>{line}</p>)}</section>;
      })}
      <Button onClick={() => navigate('/store', { replace: true })}>返回工作台</Button>
    </main>;
  }
  return <main className="technician-login-page"><section className="technician-login-card">
    <h1>正在验证企业微信身份</h1>
    <p>验证完成后进入当前账号的服务工作台。</p>
    {error ? <><Alert type="error" message={error} />
      <Button type="primary" block onClick={() => {
        if (complete) { clearStaffSession('/technician' + loginPath); navigate(loginPath === '/store/login' ? '/store/wecom' : '/wecom', { replace: true }); return; }
        pending.current = undefined; setError(''); setAttempt((value) => value + 1);
      }}>重新验证</Button></> : <Spin />}
    <Button block onClick={() => { clearStaffSession('/technician' + loginPath); navigate(loginPath, { replace: true }); }}>使用账号登录</Button>
  </section></main>;
}

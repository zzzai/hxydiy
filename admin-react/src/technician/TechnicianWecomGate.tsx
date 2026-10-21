import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Spin } from 'antd';
import { useNavigate } from 'react-router-dom';
import { getStaff } from '../api';
import { technicianMobileHome } from './technicianMobile';
import { beginWecomEntry, clearStaffSession, completeWecomEntry, wecomLoginPath } from '../wecomSession';

export default function TechnicianWecomGate({ complete = false }: { complete?: boolean }) {
  const navigate = useNavigate();
  const loginPath = useRef(wecomLoginPath()).current;
  const verifiedRole = useRef<'technician' | 'manager'>();
  const pending = useRef<Promise<boolean | void>>();
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    pending.current ||= complete ? completeWecomEntry(role => { verifiedRole.current = role; }) : beginWecomEntry();
    void pending.current.then((accepted) => {
      if (!active || !complete) return;
      if (accepted && verifiedRole.current) {
        navigate(technicianMobileHome(verifiedRole.current, getStaff()?.technician_id), { replace: true });
      }
      else setError('本次登录已失效，请重新进入企业微信工作台。');
    }).catch(() => {
      if (active) setError('企业微信身份验证未完成，请重试或使用账号登录。');
    });
    return () => { active = false; };
  }, [complete, navigate, attempt]);

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

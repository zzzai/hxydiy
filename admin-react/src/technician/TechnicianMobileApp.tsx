import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { flushSync } from 'react-dom';
import { Spin } from 'antd';
import { Navigate, BrowserRouter, Routes, Route, useLocation } from 'react-router-dom';
import { getStaff, getToken } from '../api';
import { clearStaffSession, getSessionEpoch, isWecomEntryPending, isWecomSession, subscribeSessionEpoch } from '../wecomSession';
import TechnicianMobileLoginPage from './TechnicianMobileLoginPage';
import TechnicianMobileShell from './TechnicianMobileShell';
import TechnicianTodayPage from './TechnicianTodayPage';
import TechnicianMyServicesPage from './TechnicianMyServicesPage';
import TechnicianHistoryPage from './TechnicianHistoryPage';
import TechnicianMePage from './TechnicianMePage';
import TechnicianMembershipPausedPage from './TechnicianMembershipPausedPage';
import TechnicianWecomGate from './TechnicianWecomGate';
import { technicianMobileHome } from './technicianMobile';
import './technician-mobile.css';

export { TECHNICIAN_MOBILE_ROUTES, technicianStatusLabel, technicianActions } from './technicianMobile';

function TechnicianSessionRoutes() {
  const epoch = useSyncExternalStore(subscribeSessionEpoch, getSessionEpoch);
  const location = useLocation();
  const [suspended, setSuspended] = useState(false);
  const [reverify, setReverify] = useState(false);
  const restoreIdentity = useRef(false);
  const loggedIn = !!getToken() && ['technician', 'manager'].includes(getStaff()?.role);
  const logout = clearStaffSession;
  useEffect(() => {
    const hide = () => {
      if (!isWecomSession() || getStaff()?.role !== 'technician') return;
      restoreIdentity.current = true;
      flushSync(() => { setSuspended(true); clearStaffSession(); });
    };
    const show = (event: PageTransitionEvent) => {
      if (!event.persisted || !restoreIdentity.current) return;
      restoreIdentity.current = false;
      setSuspended(false); setReverify(true);
    };
    window.addEventListener('pagehide', hide);
    window.addEventListener('pageshow', show);
    return () => { window.removeEventListener('pagehide', hide); window.removeEventListener('pageshow', show); };
  }, []);
  useEffect(() => { if (getToken() && !['technician', 'manager'].includes(getStaff()?.role)) logout(); }, [epoch]);
  useEffect(() => { setReverify(false); }, [location.pathname]);
  const manager = getStaff()?.role === 'manager';
  const home = technicianMobileHome(getStaff()?.role);
  const path = location.pathname.replace(/\/$/, '');
  if (suspended) return <main className="technician-login-page"><Spin /><p>返回后重新验证身份</p></main>;
  if (path === '/wecom/complete') return <TechnicianWecomGate key="complete" complete />;
  if (path === '/wecom' || reverify || isWecomEntryPending()) return <TechnicianWecomGate key="begin" />;
  return <Routes><Route path="/login" element={loggedIn ? <Navigate to={home} replace /> : <TechnicianMobileLoginPage key={epoch} onLogin={() => undefined} />} /><Route path="/*" element={loggedIn ? <TechnicianMobileShell key={epoch} onLogout={logout}><Routes>{!manager && <><Route path="today" element={<TechnicianMyServicesPage />} /><Route path="positions" element={<TechnicianTodayPage />} /><Route path="history" element={<TechnicianHistoryPage />} /><Route path="me" element={<TechnicianMePage />} /></>}<Route path="member-verify" element={manager ? <TechnicianMembershipPausedPage /> : <Navigate to="/today" replace />} /><Route path="*" element={<Navigate to={home} replace />} /></Routes></TechnicianMobileShell> : <Navigate to="/login" replace />} /></Routes>;
}

export default function TechnicianMobileApp() {
  return <BrowserRouter basename="/technician"><TechnicianSessionRoutes /></BrowserRouter>;
}

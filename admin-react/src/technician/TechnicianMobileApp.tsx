import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { flushSync } from 'react-dom';
import { Spin } from 'antd';
import { Navigate, BrowserRouter, Routes, Route, useLocation, useNavigate } from 'react-router-dom';
import { getStaff, getToken } from '../api';
import { clearStaffSession, getSessionEpoch, isWecomEntryPending, clearDepartingWecomSession, wecomSessionPath, subscribeSessionEpoch } from '../wecomSession';
import ManagerStorePage from './ManagerStorePage';
import { isMobileManager } from './managerMobile';
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
  const navigate = useNavigate();
  const [suspended, setSuspended] = useState(false);
  const [reverify, setReverify] = useState(false);
  const restoreIdentity = useRef(false);
  const restorePath = useRef('');
  const intentionalDesktop = useRef(false);
  const staff = getStaff();
  const technicianId = staff?.technician_id;
  const hasTechnician = Number.isInteger(technicianId) && Number(technicianId) > 0;
  const manager = isMobileManager(staff);
  const loggedIn = !!getToken() && (staff?.role === 'technician' || manager);
  const managerPath = location.pathname === '/store' || location.pathname.startsWith('/store/');
  const loginPath = managerPath ? '/store/login' : '/login';
  const logout = () => clearStaffSession();
  useEffect(() => {
    const hide = () => {
      restorePath.current = wecomSessionPath();
      flushSync(() => {
        if (!clearDepartingWecomSession(intentionalDesktop.current)) return;
        restoreIdentity.current = true;
        setSuspended(true);
      });
    };
    const show = (event: PageTransitionEvent) => {
      if (!event.persisted) return;
      if (intentionalDesktop.current && !restoreIdentity.current) {
        intentionalDesktop.current = false;
        setSuspended(false);
        return;
      }
      if (!restoreIdentity.current) return;
      restoreIdentity.current = false;
      intentionalDesktop.current = false;
      clearStaffSession(restorePath.current);
      navigate(restorePath.current.startsWith('/technician/store') ? '/store/wecom' : '/wecom', { replace: true });
      setSuspended(false); setReverify(true);
    };
    window.addEventListener('pagehide', hide);
    window.addEventListener('pageshow', show);
    return () => { window.removeEventListener('pagehide', hide); window.removeEventListener('pageshow', show); };
  }, [navigate]);
  useEffect(() => { if (getToken() && !['technician', 'manager'].includes(getStaff()?.role || '')) logout(); }, [epoch]);
  useEffect(() => { setReverify(false); }, [location.pathname]);
  const home = technicianMobileHome(staff?.role, technicianId);
  const path = location.pathname.replace(/\/$/, '');
  if (suspended) return <main className="technician-login-page"><Spin /><p>返回后重新验证身份</p></main>;
  if (path === '/wecom/complete') return <TechnicianWecomGate key="complete" complete />;
  if (path === '/wecom' || path === '/store/wecom' || reverify || isWecomEntryPending()) return <TechnicianWecomGate key="begin" />;
  const onLogin = (staff: { role?: string; technician_id?: number | null }) => navigate(technicianMobileHome(staff.role, staff.technician_id), { replace: true });
  const openDesktop = () => {
    if (!isMobileManager(getStaff())) return;
    intentionalDesktop.current = true;
    flushSync(() => setSuspended(true));
    window.location.assign('/admin/#/today');
  };
  return <Routes><Route path="/store/login" element={loggedIn && manager ? <Navigate to={home} replace /> : <TechnicianMobileLoginPage key={epoch} managerOnly onLogin={onLogin} />} /><Route path="/login" element={loggedIn ? <Navigate to={home} replace /> : <TechnicianMobileLoginPage key={epoch} onLogin={onLogin} />} /><Route path="/*" element={loggedIn ? <TechnicianMobileShell key={epoch} onLogout={logout} onOpenDesktop={openDesktop}><Routes><Route path="store" element={manager ? <ManagerStorePage /> : <Navigate to="/store/login" replace />} />{(!manager || hasTechnician) && <><Route path="today" element={<TechnicianMyServicesPage />} /><Route path="positions" element={<TechnicianTodayPage />} /><Route path="history" element={<TechnicianHistoryPage />} /><Route path="me" element={<TechnicianMePage />} /></>}<Route path="member-verify" element={manager ? <TechnicianMembershipPausedPage /> : <Navigate to="/today" replace />} /><Route path="*" element={<Navigate to={home} replace />} /></Routes></TechnicianMobileShell> : <Navigate to={loginPath} replace />} /></Routes>;
}

export default function TechnicianMobileApp() {
  return <BrowserRouter basename="/technician"><TechnicianSessionRoutes /></BrowserRouter>;
}

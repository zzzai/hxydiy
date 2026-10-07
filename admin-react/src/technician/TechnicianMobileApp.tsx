import { useEffect, useState } from 'react';
import { Navigate, BrowserRouter, Routes, Route } from 'react-router-dom';
import { getStaff, getToken } from '../api';
import TechnicianMobileLoginPage from './TechnicianMobileLoginPage';
import TechnicianMobileShell from './TechnicianMobileShell';
import TechnicianTodayPage from './TechnicianTodayPage';
import TechnicianHistoryPage from './TechnicianHistoryPage';
import TechnicianMePage from './TechnicianMePage';
import TechnicianMembershipPausedPage from './TechnicianMembershipPausedPage';
import { technicianMobileHome } from './technicianMobile';
import './technician-mobile.css';

export { TECHNICIAN_MOBILE_ROUTES, technicianStatusLabel, technicianActions } from './technicianMobile';

export default function TechnicianMobileApp() {
  const [loggedIn, setLoggedIn] = useState(() => !!getToken() && ['technician', 'manager'].includes(getStaff()?.role));
  const logout = () => { localStorage.removeItem('hxy_admin_token'); localStorage.removeItem('hxy_admin_staff'); setLoggedIn(false); };
  useEffect(() => { if (getToken() && !['technician', 'manager'].includes(getStaff()?.role)) logout(); }, []);
  const manager = getStaff()?.role === 'manager';
  const home = technicianMobileHome(getStaff()?.role);
  return <BrowserRouter basename="/technician"><Routes><Route path="/login" element={loggedIn ? <Navigate to={home} replace /> : <TechnicianMobileLoginPage onLogin={() => setLoggedIn(true)} />} /><Route path="/*" element={loggedIn ? <TechnicianMobileShell onLogout={logout}><Routes>{!manager && <><Route path="today" element={<TechnicianTodayPage />} /><Route path="history" element={<TechnicianHistoryPage />} /><Route path="me" element={<TechnicianMePage />} /></>}<Route path="member-verify" element={manager ? <TechnicianMembershipPausedPage /> : <Navigate to="/today" replace />} /><Route path="*" element={<Navigate to={home} replace />} /></Routes></TechnicianMobileShell> : <Navigate to="/login" replace />} /></Routes></BrowserRouter>;
}

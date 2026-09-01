import { useEffect, useState } from 'react';
import { Navigate, BrowserRouter, Routes, Route } from 'react-router-dom';
import { getStaff, getToken } from '../api';
import TechnicianMobileLoginPage from './TechnicianMobileLoginPage';
import TechnicianMobileShell from './TechnicianMobileShell';
import TechnicianTodayPage from './TechnicianTodayPage';
import TechnicianHistoryPage from './TechnicianHistoryPage';
import TechnicianMePage from './TechnicianMePage';
import './technician-mobile.css';

export { TECHNICIAN_MOBILE_ROUTES, technicianStatusLabel, technicianActions } from './technicianMobile';

export default function TechnicianMobileApp() {
  const [loggedIn, setLoggedIn] = useState(() => !!getToken() && getStaff()?.role === 'technician');
  const logout = () => { localStorage.removeItem('hxy_admin_token'); localStorage.removeItem('hxy_admin_staff'); setLoggedIn(false); };
  useEffect(() => { if (getToken() && getStaff()?.role !== 'technician') logout(); }, []);
  return <BrowserRouter basename="/technician"><Routes><Route path="/login" element={loggedIn ? <Navigate to="/today" replace /> : <TechnicianMobileLoginPage onLogin={() => setLoggedIn(true)} />} /><Route path="/*" element={loggedIn ? <TechnicianMobileShell onLogout={logout}><Routes><Route path="today" element={<TechnicianTodayPage />} /><Route path="history" element={<TechnicianHistoryPage />} /><Route path="me" element={<TechnicianMePage />} /><Route path="*" element={<Navigate to="/today" replace />} /></Routes></TechnicianMobileShell> : <Navigate to="/login" replace />} /></Routes></BrowserRouter>;
}

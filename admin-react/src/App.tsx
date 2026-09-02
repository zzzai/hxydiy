import { useState, useEffect } from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import { App as AntApp, Spin } from 'antd';
import LoginPage from './pages/LoginPage';
import MainLayout from './layouts/MainLayout';
import { getStaff, getToken, setApiErrorHandler } from './api';
import { isTechnicianEntry } from './auth';
import TechnicianMobileApp from './technician/TechnicianMobileApp';
import { dataProvider } from './core/dataProvider';

export default function App() {
  const { message } = AntApp.useApp();
  const [checking, setChecking] = useState(true);
  const [loggedIn, setLoggedIn] = useState(false);

  useEffect(() => {
    setApiErrorHandler((text) => message.error(text));
    return () => setApiErrorHandler(() => undefined);
  }, [message]);

  useEffect(() => {
    setLoggedIn(!!getToken());
    dataProvider.setStoreId(getStaff()?.store_id);
    setChecking(false);
  }, []);

  const handleLogin = () => {
    dataProvider.setStoreId(getStaff()?.store_id);
    setLoggedIn(true);
  };

  if (checking) return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}><Spin size="large" /></div>;

  if (isTechnicianEntry()) return <TechnicianMobileApp />;

  if (loggedIn && getStaff()?.role === 'technician') {
    window.location.replace('/technician/today');
    return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}><Spin size="large" /></div>;
  }

  return (
    <HashRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/login" element={!loggedIn ? <LoginPage onLogin={handleLogin} /> : <Navigate to="/" />} />
        <Route path="/*" element={loggedIn ? <MainLayout onLogout={() => { localStorage.clear(); dataProvider.setStoreId(null); setLoggedIn(false); }} /> : <Navigate to="/login" />} />
      </Routes>
    </HashRouter>
  );
}

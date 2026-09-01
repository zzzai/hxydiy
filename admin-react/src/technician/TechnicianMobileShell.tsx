import { useEffect, useState } from 'react';
import { App, Button, Spin } from 'antd';
import { CalendarOutlined, ClockCircleOutlined, LogoutOutlined, UserOutlined } from '@ant-design/icons';
import { useLocation, useNavigate } from 'react-router-dom';
import { getTechnicianMe } from '../api';

const tabs = [
  { path: '/technician/today', label: '今日服务', icon: <CalendarOutlined /> },
  { path: '/technician/history', label: '服务记录', icon: <ClockCircleOutlined /> },
  { path: '/technician/me', label: '我的', icon: <UserOutlined /> },
];

export default function TechnicianMobileShell({ children, onLogout }: { children: React.ReactNode; onLogout: () => void }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { message } = App.useApp();
  const [me, setMe] = useState<any>();
  useEffect(() => { void getTechnicianMe().then((res) => setMe(res.data)).catch(() => undefined); }, []);
  const staff = me?.staff || me?.technician?.staff || JSON.parse(localStorage.getItem('hxy_admin_staff') || 'null');
  const logout = () => { onLogout(); message.success('已退出登录'); navigate('/technician/login', { replace: true }); };
  return (
    <div className="technician-mobile-app">
      <header className="technician-mobile-header">
        <div><strong>{staff?.store_name || me?.store?.name || '当前门店'}</strong><span>{me?.technician?.name || staff?.name || '技师'}</span></div>
        <Button type="text" aria-label="退出登录" icon={<LogoutOutlined />} onClick={logout} />
      </header>
      <main className="technician-mobile-content">{children}</main>
      <nav className="technician-mobile-tabbar" aria-label="技师端导航">
        {tabs.map((tab) => <button key={tab.path} className={location.pathname === tab.path ? 'active' : ''} onClick={() => navigate(tab.path)}>{tab.icon}<span>{tab.label}</span></button>)}
      </nav>
    </div>
  );
}

import { useEffect, useState } from 'react';
import { App, Button } from 'antd';
import { CalendarOutlined, ClockCircleOutlined, LogoutOutlined, ShopOutlined, UserOutlined } from '@ant-design/icons';
import { useLocation, useNavigate } from 'react-router-dom';
import { getStaff, getTechnicianMe } from '../api';
import { isMobileManager } from './managerMobile';
import { technicianMobileTabs, TECHNICIAN_MOBILE_TAB_PATHS } from './technicianMobile';

const tabs = [
  { path: TECHNICIAN_MOBILE_TAB_PATHS[0], label: '今日服务', icon: <CalendarOutlined /> },
  { path: TECHNICIAN_MOBILE_TAB_PATHS[1], label: '服务记录', icon: <ClockCircleOutlined /> },
  { path: TECHNICIAN_MOBILE_TAB_PATHS[2], label: '我的', icon: <UserOutlined /> },
  { path: '/store', label: '门店', icon: <ShopOutlined /> },
];

export default function TechnicianMobileShell({ children, onLogout, onOpenDesktop }: { children: React.ReactNode; onLogout: () => void; onOpenDesktop?: () => void }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { message } = App.useApp();
  const [me, setMe] = useState<any>();
  const manager = isMobileManager(getStaff());
  const managerTechnician = manager && Boolean(getStaff()?.technician_id);
  useEffect(() => {
    if (manager && !managerTechnician) return;
    let active = true;
    void getTechnicianMe().then((res) => { if (active) setMe(res.data); }).catch(() => undefined);
    return () => { active = false; };
  }, [manager, managerTechnician]);
  const staff = me?.staff || me?.technician?.staff || getStaff();
  const visiblePaths = technicianMobileTabs(staff?.role, staff?.technician_id);
  const visibleTabs = tabs.filter((tab) => visiblePaths.includes(tab.path) || (manager && tab.path === '/store'));
  const logout = () => { onLogout(); message.success('已退出登录'); navigate(manager ? '/store/login' : '/login', { replace: true }); };
  return (
    <div className={'technician-mobile-app' + (manager ? ' manager-mobile-app' : '')}>
      <header className="technician-mobile-header">
        <div><strong>{staff?.store_name || me?.store?.name || '当前门店'}</strong><span>{me?.technician?.name || staff?.name || (manager ? '店长' : '技师')}</span></div>
        <>{manager ? <details className="manager-mobile-more"><summary>更多</summary><div><button onClick={onOpenDesktop}>电脑后台</button><button onClick={logout}>退出登录</button></div></details> : <Button type="text" aria-label="退出登录" icon={<LogoutOutlined />} onClick={logout} />}</>
      </header>
      <main className="technician-mobile-content">{children}</main>
      {visibleTabs.length > 0 && <nav className="technician-mobile-tabbar" aria-label="技师端导航" style={{ gridTemplateColumns: `repeat(${visibleTabs.length}, 1fr)` }}>
        {visibleTabs.map((tab) => <button key={tab.path} className={location.pathname === tab.path ? 'active' : ''} onClick={() => navigate(tab.path)}>{tab.icon}<span>{tab.label}</span></button>)}
      </nav>}
    </div>
  );
}

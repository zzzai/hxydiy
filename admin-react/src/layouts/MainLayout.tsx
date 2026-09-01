import { lazy, Suspense, useState, Component, type ReactNode } from 'react';
import { Navigate, Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Typography, Button, Dropdown, Drawer, Grid, Result } from 'antd';
import {
  DashboardOutlined, OrderedListOutlined, BarChartOutlined, DesktopOutlined,
  AppstoreOutlined, GiftOutlined, TeamOutlined, ThunderboltOutlined, LogoutOutlined,
  UserOutlined, MenuFoldOutlined, MenuUnfoldOutlined, MenuOutlined, EnvironmentOutlined,
  IdcardOutlined, ProjectOutlined, ShoppingOutlined, TagsOutlined, PieChartOutlined,
  RobotOutlined, FileSearchOutlined, MessageOutlined,
} from '@ant-design/icons';
import { getStaff } from '../api';
import { getDefaultPath, getVisibleMenuPaths, isPathAllowed } from '../auth';
import { getStoreContextLabel } from '../core/auth/storeContext';
import { getVisibleNavigationGroups } from '../core/navigation/index.ts';

const PageContentPage = lazy(() => import('../pages/PageContentPage'));
const TodayPage = lazy(() => import('../pages/TodayPage'));
const OrdersPage = lazy(() => import('../pages/OrdersPage'));
const AnalyticsPage = lazy(() => import('../pages/AnalyticsPage'));
const AuditLogsPage = lazy(() => import('../pages/AuditLogsPage'));
const FeedbackPage = lazy(() => import('../pages/FeedbackPage'));
const RoomsPage = lazy(() => import('../pages/RoomsPage'));
const TechsPage = lazy(() => import('../pages/TechsPage'));
const ProjectsPage = lazy(() => import('../pages/ProjectsPage'));
const AddonsPage = lazy(() => import('../pages/AddonsPage'));
const ProductsPage = lazy(() => import('../pages/ProductsPage'));
const CouponsPage = lazy(() => import('../pages/CouponsPage'));
const UsersPage = lazy(() => import('../pages/UsersPage'));
const TagsPage = lazy(() => import('../pages/TagsPage'));
const SegmentsPage = lazy(() => import('../pages/SegmentsPage'));
const AutomationPage = lazy(() => import('../pages/AutomationPage'));
const SelectionSessionsPage = lazy(() => import('../pages/SelectionSessionsPage'));
const ServicePositionsPage = lazy(() => import('../pages/ServicePositionsPage'));
const StoresPage = lazy(() => import('../pages/StoresPage'));

const { Sider, Content } = Layout;

class ErrorBoundary extends Component<{ children: React.ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(e: Error) { return { error: e }; }
  render() {
    if (this.state.error) return <div style={{ padding: 40, color: '#c0392b' }}><h3>页面出错</h3><pre>{this.state.error.message}</pre></div>;
    return this.props.children;
  }
}

const icons: Record<string, ReactNode> = {
  dashboard: <DashboardOutlined />, 'ordered-list': <OrderedListOutlined />, 'bar-chart': <BarChartOutlined />,
  desktop: <DesktopOutlined />, appstore: <AppstoreOutlined />, gift: <GiftOutlined />, team: <TeamOutlined />,
  thunderbolt: <ThunderboltOutlined />, environment: <EnvironmentOutlined />, idcard: <IdcardOutlined />,
  project: <ProjectOutlined />, shopping: <ShoppingOutlined />, tags: <TagsOutlined />, 'pie-chart': <PieChartOutlined />,
  robot: <RobotOutlined />, 'file-search': <FileSearchOutlined />, message: <MessageOutlined />,
};

export default function MainLayout({ onLogout }: { onLogout: () => void }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const staff = getStaff();
  const role = staff?.role;
  const visibleMenuGroups = getVisibleNavigationGroups(role, staff?.store_id);
  const screens = Grid.useBreakpoint();
  const isMobile = !screens.md;
  const selectedKeys = [location.pathname];
  const openKeys = visibleMenuGroups.map(g => g.key);

  const page = (path: string, element: React.ReactNode) => (
    isPathAllowed(role, path, staff?.store_id) ? element : <Navigate to="/forbidden" replace />
  );

  const navigation = (
    <>
      <div className="brand-block">
        <span className="brand-mark">荷</span>
        {(!collapsed || isMobile) && <span className="brand-name">荷小悦门店中台</span>}
      </div>
      <Menu
        theme="dark"
        mode="inline"
        selectedKeys={selectedKeys}
        defaultOpenKeys={openKeys}
        onClick={({ key }) => { navigate(key); setMobileMenuOpen(false); }}
        items={visibleMenuGroups.map((group) => ({
          key: group.key,
          icon: icons[group.icon],
          label: group.label,
          children: group.items.map((item) => ({ key: item.path, icon: icons[item.icon], label: item.label })),
        }))}
        className="main-menu"
      />
    </>
  );

  return (
    <ErrorBoundary>
      <Layout className="app-shell">
        {!isMobile && <Sider trigger={null} collapsible collapsed={collapsed} width={240} className="desktop-sider" theme="dark">{navigation}</Sider>}
        <Drawer open={isMobile && mobileMenuOpen} onClose={() => setMobileMenuOpen(false)} placement="left" width={288} closable={false} styles={{ body: { padding: 0, background: '#0d2f29' } }}>
          {navigation}
        </Drawer>
        <Layout>
          <header className="topbar">
            <Button
              type="text"
              aria-label={isMobile ? '打开导航' : '折叠导航'}
              icon={isMobile ? <MenuOutlined /> : (collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />)}
              onClick={() => isMobile ? setMobileMenuOpen(true) : setCollapsed(!collapsed)}
            />
            <div className="topbar-actions">
              <Typography.Text className="store-name">{getStoreContextLabel(staff)}</Typography.Text>
              <Dropdown menu={{ items: [{ key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: onLogout }] }}>
                <Button type="text" icon={<UserOutlined />} className="staff-button">
                  {staff?.name || '员工'} {!isMobile && <Typography.Text type="secondary" style={{ fontSize: 12, marginLeft: 4 }}>{staff?.role === 'admin' ? '管理员' : staff?.role === 'manager' ? '店长' : '店员'}</Typography.Text>}
                </Button>
              </Dropdown>
            </div>
          </header>
          <Content className="app-content">
            <Suspense fallback={<div className="page-loading" aria-live="polite">页面加载中...</div>}>
              <Routes>
                <Route path="/" element={<Navigate to={getDefaultPath(role, staff?.store_id)} replace />} />
                <Route path="/today" element={page('/today', <TodayPage />)} />
                <Route path="/service-positions" element={page('/service-positions', <ServicePositionsPage />)} />
                <Route path="/selection-sessions" element={page('/selection-sessions', <SelectionSessionsPage />)} />
                <Route path="/orders" element={page('/orders', <OrdersPage />)} />
                <Route path="/analytics" element={page('/analytics', <AnalyticsPage />)} />
                <Route path="/audit-logs" element={page('/audit-logs', <AuditLogsPage />)} />
                <Route path="/feedback" element={page('/feedback', <FeedbackPage />)} />
                <Route path="/rooms/*" element={page('/rooms', <RoomsPage />)} />
                <Route path="/stores" element={page('/stores', <StoresPage />)} />
                <Route path="/techs" element={page('/techs', <TechsPage />)} />
                <Route path="/projects" element={page('/projects', <ProjectsPage />)} />
                <Route path="/addons" element={page('/addons', <AddonsPage />)} />
                <Route path="/page-content" element={page('/page-content', <PageContentPage />)} />
                <Route path="/products" element={page('/products', <ProductsPage />)} />
                <Route path="/coupons" element={page('/coupons', <CouponsPage />)} />
                <Route path="/users" element={page('/users', <UsersPage />)} />
                <Route path="/tags" element={page('/tags', <TagsPage />)} />
                <Route path="/segments" element={page('/segments', <SegmentsPage />)} />
                <Route path="/automation" element={page('/automation', <AutomationPage />)} />
                <Route path="/forbidden" element={<Result status="403" title="无权访问" subTitle="当前账号没有此页面的访问权限" extra={<Button type="primary" onClick={() => navigate(getDefaultPath(role, staff?.store_id))}>返回可用页面</Button>} />} />
                <Route path="*" element={<Navigate to={getDefaultPath(role, staff?.store_id)} replace />} />
              </Routes>
            </Suspense>
          </Content>
        </Layout>
      </Layout>
    </ErrorBoundary>
  );
}

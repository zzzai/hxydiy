export type NavigationRole = 'admin' | 'manager' | 'staff' | 'technician';

export type NavigationItem = {
  path: string;
  label: string;
  icon: string;
  roles: readonly NavigationRole[];
  requiresUnboundAdmin?: boolean;
};

export type NavigationGroup = {
  key: string;
  label: string;
  icon: string;
  items: readonly NavigationItem[];
};

const managementRoles = ['admin', 'manager'] as const;
const storeRoles = ['admin', 'manager', 'staff'] as const;

export const adminNavigationGroups: readonly NavigationGroup[] = [
  {
    key: 'operations',
    label: '今日运营',
    icon: 'dashboard',
    items: [
      { path: '/today', label: '今日运营', icon: 'ordered-list', roles: storeRoles },
      { path: '/service-positions', label: '服务位看板', icon: 'environment', roles: storeRoles },
      { path: '/selection-sessions', label: '到店服务选单', icon: 'project', roles: storeRoles },
      { path: '/orders', label: '结算记录', icon: 'ordered-list', roles: storeRoles },
      { path: '/analytics', label: '经营分析', icon: 'bar-chart', roles: managementRoles },
      { path: '/audit-logs', label: '审计日志', icon: 'file-search', roles: managementRoles },
      { path: '/feedback', label: '低分评价', icon: 'message', roles: managementRoles },
    ],
  },
  {
    key: 'catalog',
    label: '服务与商品',
    icon: 'appstore',
    items: [
      { path: '/projects', label: '服务项目', icon: 'project', roles: managementRoles },
      { path: '/addons', label: '项目加项', icon: 'tags', roles: managementRoles },
      { path: '/products', label: '商城商品', icon: 'shopping', roles: managementRoles },
      { path: '/page-content', label: 'DIY 页面配置', icon: 'appstore', roles: managementRoles },
    ],
  },
  {
    key: 'people',
    label: '人员与顾客',
    icon: 'team',
    items: [
      { path: '/techs', label: '技师管理', icon: 'idcard', roles: storeRoles },
      { path: '/users', label: '用户列表', icon: 'team', roles: managementRoles },
      { path: '/tags', label: '标签管理', icon: 'tags', roles: managementRoles },
      { path: '/segments', label: '用户分群', icon: 'pie-chart', roles: managementRoles },
    ],
  },
  {
    key: 'store',
    label: '门店与资源',
    icon: 'desktop',
    items: [
      { path: '/stores', label: '门店主数据', icon: 'environment', roles: ['admin'], requiresUnboundAdmin: true },
      { path: '/rooms', label: '房间/床位', icon: 'environment', roles: storeRoles },
    ],
  },
  {
    key: 'marketing',
    label: '营销',
    icon: 'gift',
    items: [
      { path: '/coupons', label: '优惠券', icon: 'gift', roles: managementRoles },
    ],
  },
  {
    key: 'system',
    label: '系统',
    icon: 'thunderbolt',
    items: [
      { path: '/automation', label: 'SCRM 规则', icon: 'robot', roles: managementRoles },
    ],
  },
];

function isVisible(item: NavigationItem, role?: string, storeId?: number | null): boolean {
  if (!role || !item.roles.includes(role as NavigationRole)) return false;
  return !item.requiresUnboundAdmin || (role === 'admin' && !storeId);
}

export function getVisibleNavigationGroups(role?: string, storeId?: number | null): NavigationGroup[] {
  return adminNavigationGroups
    .map((group) => ({ ...group, items: group.items.filter((item) => isVisible(item, role, storeId)) }))
    .filter((group) => group.items.length > 0);
}

export function getNavigationPaths(role?: string, storeId?: number | null): string[] {
  const paths = getVisibleNavigationGroups(role, storeId).flatMap((group) => group.items.map((item) => item.path));
  if (role === 'staff') {
    const legacyOrder = ['/today', '/service-positions', '/selection-sessions', '/orders', '/rooms', '/techs'];
    return paths.sort((left, right) => legacyOrder.indexOf(left) - legacyOrder.indexOf(right));
  }
  return paths;
}

export function isNavigationPathAllowed(role: string | undefined, pathname: string, storeId?: number | null): boolean {
  return getNavigationPaths(role, storeId).some((path) => pathname === path || pathname.startsWith(`${path}/`));
}

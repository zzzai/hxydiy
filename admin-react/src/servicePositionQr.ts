export type ServicePositionQrAction = 'enable' | 'disable' | 'regenerate' | 'rebind';

export type ServicePositionQrPermissions = {
  canView: boolean;
  canManage: boolean;
};

export function getServicePositionQrPermissions(role?: string): ServicePositionQrPermissions {
  const canView = role === 'admin' || role === 'manager' || role === 'staff';
  return {
    canView,
    canManage: role === 'manager',
  };
}

export function servicePositionQrActions(status: string, replaced: boolean): ServicePositionQrAction[] {
  if (replaced) return [];
  return status === 'active'
    ? ['disable', 'regenerate', 'rebind']
    : ['enable', 'regenerate', 'rebind'];
}

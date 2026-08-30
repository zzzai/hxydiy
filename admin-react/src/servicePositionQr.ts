export type ServicePositionQrAction = 'enable' | 'disable' | 'regenerate' | 'rebind';

export function servicePositionQrActions(status: string, replaced: boolean): ServicePositionQrAction[] {
  if (replaced) return [];
  return status === 'active'
    ? ['disable', 'regenerate', 'rebind']
    : ['enable', 'regenerate', 'rebind'];
}

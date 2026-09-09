import { canManageConfiguration } from './auth.ts';

export function canManageServicePositionConfiguration(role?: string): boolean {
  return canManageConfiguration(role);
}

export function buildServicePositionConfigurationPayload(maintenanceNote: string, displayOrder: number) {
  return {
    maintenance_note: maintenanceNote,
    display_order: displayOrder,
  };
}

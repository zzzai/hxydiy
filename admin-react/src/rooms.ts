export type RoomConfigurationAction =
  | { type: 'open'; roomId: number }
  | { type: 'close' };

export type RoomOperationalAction = 'enable' | 'disable' | null;

export type RoomOperationalSummary = {
  operational_status?: string | null;
  status?: string | null;
  is_service_position?: boolean;
  is_space_container?: boolean;
};

export function getRoomOperationalAction(room: RoomOperationalSummary): RoomOperationalAction {
  if (room.is_service_position === false || room.is_space_container === true) return null;
  const operationalStatus = room.operational_status || 'active';
  if (operationalStatus === 'inactive') return 'enable';
  if (operationalStatus === 'active' && (room.status || 'available') === 'available') return 'disable';
  return null;
}

export function roomConfigurationReducer(
  _currentRoomId: number | null,
  action: RoomConfigurationAction,
): number | null {
  return action.type === 'open' ? action.roomId : null;
}

export function mergeRoomConfigurationData<T extends Record<string, unknown>>(
  summary: T,
  detail: Record<string, unknown>,
): T & Record<string, unknown> {
  const availableDetail = Object.fromEntries(
    Object.entries(detail).filter(([, value]) => value !== undefined && value !== null && value !== ''),
  );
  return { ...summary, ...availableDetail };
}

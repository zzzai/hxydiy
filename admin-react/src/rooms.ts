export type RoomConfigurationAction =
  | { type: 'open'; roomId: number }
  | { type: 'close' };

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

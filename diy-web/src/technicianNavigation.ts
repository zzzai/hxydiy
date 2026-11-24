import { createOverlayHistoryState, readOverlayHistoryStack } from './overlayHistory.ts';

export type TechnicianView = { storeId: number; projectId?: number; profile?: string; photo?: number };

export function technicianViewState(current: unknown, view: TechnicianView, replace = false) {
  const state = replace && readOverlayHistoryStack(current).at(-1) === 'technicians'
    ? current as Record<string, unknown>
    : createOverlayHistoryState(current, 'technicians');
  return { ...state, hxyTechnicianView: view };
}

export function readTechnicianView(state: unknown, storeId: number): TechnicianView | null {
  if (readOverlayHistoryStack(state).at(-1) !== 'technicians') return null;
  const value = (state as { hxyTechnicianView?: TechnicianView }).hxyTechnicianView;
  return value?.storeId === storeId ? value : null;
}

export function technicianBackSteps(state: unknown): number {
  const stack = readOverlayHistoryStack(state);
  let count = 0;
  for (let i = stack.length - 1; i >= 0 && stack[i] === 'technicians'; i--) count++;
  return count;
}

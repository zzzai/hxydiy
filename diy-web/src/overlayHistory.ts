export const OVERLAY_HISTORY_KINDS = [
  'feedback',
  'record-login',
  'coupon-login',
  'saving-hint',
  'selection-summary',
  'project-detail',
  'local-detail',
  'tea-detail',
  'seat-map',
  'profile',
  'membership',
] as const;

export type OverlayHistoryKind = (typeof OVERLAY_HISTORY_KINDS)[number];

const OVERLAY_STACK_KEY = 'hxyDiyOverlayStack';
const OVERLAY_KEY = 'hxyDiyOverlay';
const OVERLAY_ROOT_KEY = 'hxyDiyNavigationRoot';
const OVERLAY_GUARD_KEY = 'hxyDiyNavigationGuard';

function baseState(current: unknown): Record<string, unknown> {
  return current && typeof current === 'object' && !Array.isArray(current)
    ? current as Record<string, unknown>
    : {};
}

export function createOverlayHistoryState(current: unknown, overlay: OverlayHistoryKind): Record<string, unknown> {
  const base = baseState(current);
  const stack = readOverlayHistoryStack(base);
  return { ...base, [OVERLAY_KEY]: overlay, [OVERLAY_STACK_KEY]: [...stack, overlay] };
}

export function createOverlayRootState(current: unknown): Record<string, unknown> {
  const base = baseState(current);
  const {
    [OVERLAY_KEY]: _overlay,
    [OVERLAY_STACK_KEY]: _stack,
    [OVERLAY_GUARD_KEY]: _guard,
    ...rest
  } = base;
  return { ...rest, [OVERLAY_ROOT_KEY]: true, [OVERLAY_GUARD_KEY]: false };
}

export function createOverlayGuardState(current: unknown): Record<string, unknown> {
  return { ...createOverlayRootState(current), [OVERLAY_GUARD_KEY]: true };
}

export function isOverlayRootState(state: unknown): boolean {
  return Boolean(baseState(state)[OVERLAY_ROOT_KEY]);
}

export function isOverlayGuardState(state: unknown): boolean {
  const base = baseState(state);
  return base[OVERLAY_ROOT_KEY] === true && base[OVERLAY_GUARD_KEY] === true;
}

export function replaceOverlayHistoryState(current: unknown, overlay: OverlayHistoryKind): Record<string, unknown> {
  const base = baseState(current);
  const stack = readOverlayHistoryStack(base);
  const nextStack = stack.length > 0 ? [...stack.slice(0, -1), overlay] : [overlay];
  return { ...base, [OVERLAY_KEY]: overlay, [OVERLAY_STACK_KEY]: nextStack };
}

export function readOverlayHistoryStack(state: unknown): OverlayHistoryKind[] {
  if (!state || typeof state !== 'object' || Array.isArray(state)) return [];
  const record = state as Record<string, unknown>;
  const stack = record[OVERLAY_STACK_KEY];
  if (Array.isArray(stack) && stack.every((item): item is OverlayHistoryKind => (
    typeof item === 'string' && OVERLAY_HISTORY_KINDS.includes(item as OverlayHistoryKind)
  ))) {
    return [...stack];
  }
  const current = record[OVERLAY_KEY];
  return typeof current === 'string' && OVERLAY_HISTORY_KINDS.includes(current as OverlayHistoryKind)
    ? [current as OverlayHistoryKind]
    : [];
}

export function readOverlayHistoryState(state: unknown): OverlayHistoryKind | null {
  return readOverlayHistoryStack(state).at(-1) ?? null;
}

export function shouldRunDeferredSwipeBack(before: unknown, current: unknown): boolean {
  const beforeStack = readOverlayHistoryStack(before);
  const currentStack = readOverlayHistoryStack(current);
  return beforeStack.length > 0
    && beforeStack.length === currentStack.length
    && beforeStack.every((overlay, index) => overlay === currentStack[index]);
}

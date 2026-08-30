export type TouchPoint = {
  x: number;
  y: number;
};

const EDGE_WIDTH = 48;
const MIN_HORIZONTAL_DISTANCE = 48;
const MAX_VERTICAL_DISTANCE = 56;

export function isEdgeSwipeBack(start: TouchPoint, end: TouchPoint): boolean {
  const horizontalDistance = end.x - start.x;
  const verticalDistance = Math.abs(end.y - start.y);
  return start.x <= EDGE_WIDTH
    && horizontalDistance >= MIN_HORIZONTAL_DISTANCE
    && verticalDistance <= MAX_VERTICAL_DISTANCE
    && horizontalDistance > verticalDistance * 1.15;
}

export function shouldReturnToProjectListFromSubmittedScreen(
  isSubmittedScreen: boolean,
  hasActiveOverlay: boolean,
  start: TouchPoint,
  end: TouchPoint,
): boolean {
  return isSubmittedScreen && !hasActiveOverlay && isEdgeSwipeBack(start, end);
}

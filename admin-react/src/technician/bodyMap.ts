import type { V5BodyRegion, V5BodySide } from './serviceReference';

export type BodyMapPoint = { region: V5BodyRegion; side: V5BodySide };

export function bodyMapPointKey(point: BodyMapPoint) {
  return `${point.region}:${point.side}`;
}

export function toggleBodyMapPoint(selected: BodyMapPoint[], point: BodyMapPoint): BodyMapPoint[] {
  const key = bodyMapPointKey(point);
  if (selected.some((item) => bodyMapPointKey(item) === key)) {
    return selected.filter((item) => bodyMapPointKey(item) !== key);
  }
  return selected.length >= 3 ? selected : [...selected, point];
}

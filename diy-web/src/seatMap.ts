import type { ServicePosition } from './api';

export function groupSofasBySide(positions: ServicePosition[]): { left: ServicePosition[]; right: ServicePosition[] } {
  const sofas = positions
    .filter((position) => position.type === 'sofa')
    .sort((left, right) => left.map_y - right.map_y || left.sort_order - right.sort_order);
  return {
    left: sofas.filter((position) => position.map_x < 0.5),
    right: sofas.filter((position) => position.map_x >= 0.5),
  };
}

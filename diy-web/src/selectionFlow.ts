import type { Occupancy, SelectionSession } from './api';

type SessionStatus = SelectionSession['status'];
type OccupancyStatus = Occupancy['status'] | undefined;

export function expiredSelectionCopy() {
  return {
    title: '本次位置已释放',
    message: '请重新扫码选择所在位置，或联系前台协助处理。',
  } as const;
}

export function canEditSelection(status: SessionStatus | undefined, occupancyStatus: OccupancyStatus): boolean {
  if (!status || status === 'cancelled' || status === 'expired') return false;
  if (occupancyStatus === 'post_service_present' || occupancyStatus === 'cleaning' || occupancyStatus === 'released') return false;
  // 提交后等待服务或服务进行中允许顾客追加项目；原已提交项目由后端修订接口保留。
  if (status === 'submitted') {
    return occupancyStatus === 'held'
      || occupancyStatus === 'waiting_service'
      || occupancyStatus === 'in_service';
  }
  // 前台确认后，只有服务进行中才允许顾客追加项目；其他已确认阶段由前台处理。
  if (status === 'confirmed') return occupancyStatus === 'in_service';
  return true;
}

export function shouldPreserveOccupancyAfterRevision(occupancyStatus: OccupancyStatus): boolean {
  return occupancyStatus === 'in_service';
}

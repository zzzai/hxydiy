import type { Occupancy, SelectionSession } from './api.ts';
import { canEditSelection } from './selectionFlow.ts';

type SubmittedSelectionRestoreInput = {
  draftClearedAfterSubmit?: boolean;
  sessionStatus: SelectionSession['status'];
  occupancyStatus: Occupancy['status'] | undefined;
};

type StoredEntryRestartInput = {
  requestedPositionFound: boolean;
  hasActiveOccupancy: boolean;
};

/**
 * localStorage 只用于恢复浏览器上下文，不能覆盖服务端实时占用事实。
 * 请求的服务位仍存在但已经没有活动占用时，旧记录对应的服务已经释放，
 * 应重新走入店流程创建空白选购会话，而不是继续恢复旧订单。
 */
export function shouldRestartStoredEntry({
  requestedPositionFound,
  hasActiveOccupancy,
}: StoredEntryRestartInput): boolean {
  return requestedPositionFound && !hasActiveOccupancy;
}

export function shouldHydrateStoredSelection({
  draftClearedAfterSubmit,
  sessionStatus,
  occupancyStatus,
}: SubmittedSelectionRestoreInput): boolean {
  // 提交成功后返回菜单会明确清空追加草稿；可编辑状态不应让旧项目重新出现在底部。
  if (draftClearedAfterSubmit && sessionStatus === 'submitted') return false;
  return !draftClearedAfterSubmit || (
    sessionStatus === 'confirmed' && occupancyStatus === 'in_service'
  ) || canEditSelection(sessionStatus, occupancyStatus);
}

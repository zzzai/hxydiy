import type { Occupancy, SelectionSession } from './api.ts';
import { canEditSelection } from './selectionFlow.ts';

type SubmittedSelectionRestoreInput = {
  draftClearedAfterSubmit?: boolean;
  sessionStatus: SelectionSession['status'];
  occupancyStatus: Occupancy['status'] | undefined;
};

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

import type { Occupancy, SelectionSession } from './api';
import { mergeSubmittedSelectionItems, type SelectionItem } from './domain.ts';

type SessionStatus = SelectionSession['status'];
type OccupancyStatus = Occupancy['status'] | undefined;

export function revisionItems(status: SessionStatus, original: Array<SelectionItem & { item_kind?: string; source_project_id?: number }>, draft: SelectionItem[]): SelectionItem[] {
  if (status !== 'submitted' && status !== 'confirmed') return draft;
  // The API expands these units from the retained parent choices itself.
  const explicit = original.filter(item => !(['catalog_linked_project', 'dedicated_option'].includes(item.item_kind || '')
    && original.some(parent => parent.project_id === item.source_project_id && parent.catalog_version_id)
    && !draft.some(added => added.project_id === item.project_id)));
  return mergeSubmittedSelectionItems(explicit, draft);
}

export function selectionRequestAccess(status: SessionStatus, ownerToken: string, collaboratorToken: string, version: number, authToken?: string) {
  if (status === 'draft') return collaboratorToken ? { collaborationToken: collaboratorToken, expectedVersion: version, authToken } : { authToken };
  return ownerToken ? { authToken } : null;
}

export function submittedSelectionAccess(ownerToken: string, collaboratorToken: string): { collaborationToken: string; collaborationMode: 'browse_only' | '' } {
  return ownerToken ? { collaborationToken: '', collaborationMode: '' } : { collaborationToken: collaboratorToken, collaborationMode: 'browse_only' };
}

export function expiredSelectionCopy() {
  return {
    title: '本次位置已释放',
    message: '请重新扫码选择所在位置，或联系前台协助处理。',
  } as const;
}

// 服务号无座菜单没有座位可释放；草稿接口的 409 应重建私有草稿，而不是展示座位释放页。
export function shouldRecoverPublicDraft(error: { status?: number; code?: string } | null | undefined, publicBrowsing: boolean): boolean {
  return Boolean(publicBrowsing && error?.status === 409 && error.code !== 'CART_VERSION_CONFLICT');
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

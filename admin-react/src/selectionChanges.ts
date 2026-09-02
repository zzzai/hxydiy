export type SelectionChangeState =
  | 'awaiting_staff_confirmation'
  | 'approved'
  | 'rejected'
  | string;

export type SelectionChangeItem = {
  name?: string;
  quantity?: number;
  diy_preferences?: string[];
};

export function canApproveSelectionChange(state: SelectionChangeState): boolean {
  return state === 'awaiting_staff_confirmation';
}

export function canRejectSelectionChange(state: SelectionChangeState): boolean {
  return state === 'awaiting_staff_confirmation';
}

export function selectionChangeItemSummary(item: SelectionChangeItem): string {
  const name = item.name || '服务项目';
  const quantity = Number(item.quantity || 1);
  const quantityText = quantity > 1 ? ` ×${quantity}` : '';
  const preferenceText = item.diy_preferences?.length ? ` · ${item.diy_preferences.join(' · ')}` : '';
  return `${name}${quantityText}${preferenceText}`;
}

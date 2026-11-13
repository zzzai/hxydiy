type ReceiptLike = {
  available?: boolean;
  has_conflict?: boolean;
  last_success?: { successful_submit_at?: string | null } | null;
  latest_attempt?: {
    status?: string | null;
    blocked_reason?: string | null;
    current_processing?: { current_status_label?: string | null; current_status_detail?: string | null } | null;
  } | null;
};

export function receiptBlockedLabel(reason?: string | null) {
  if (!reason) return '历史未记录';
  if (reason.includes('login')) return '等待重新登录';
  if (reason.includes('authorization')) return '等待特定授权';
  if (reason.includes('protection') || reason.includes('baseline')) return '保护基线校验未通过';
  if (reason.includes('conflict')) return '证据冲突';
  return '已阻塞';
}

export function receiptCurrentLabel(receipt?: ReceiptLike | null) {
  return receipt?.latest_attempt?.current_processing?.current_status_label || '待核实';
}

export function receiptAlertType(receipt?: ReceiptLike | null): 'error' | 'warning' | 'info' {
  if (receipt?.has_conflict) return 'error';
  if (receipt?.latest_attempt?.status === 'blocked') return 'warning';
  return 'info';
}

export function receiptAlertTitle(receipt?: ReceiptLike | null) {
  if (receipt?.has_conflict) return '会员同步回执存在冲突，待核实';
  if (receipt?.last_success) return `会员同步状态：有历史成功回执${receipt?.latest_attempt?.current_processing?.current_status_label ? ` · ${receipt.latest_attempt.current_processing.current_status_label}` : ''}`;
  return '会员同步状态：待核实';
}

export function receiptSubmissionLabel(value: unknown): '已提交' | '未提交' | '未记录' {
  if (value === true) return '已提交';
  if (value === false) return '未提交';
  return '未记录';
}

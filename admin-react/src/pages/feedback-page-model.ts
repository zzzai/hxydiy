export type FeedbackType = 'service_review' | 'visit_feedback';

export type FeedbackSource = {
  feedback_type: FeedbackType;
  source: string;
  selection_session_id?: string | null;
};

export const feedbackTypeLabel = (value: FeedbackType) => value === 'service_review' ? '服务评价' : '到店反馈';

export const feedbackSourceLabel = (row: FeedbackSource) => {
  if (row.feedback_type === 'service_review') return '已完成服务';
  if (row.source === 'personal_qr' || row.source === 'room_qr') return '服务位二维码';
  return '门店二维码';
};

export const feedbackUsesServiceLink = (row: Pick<FeedbackSource, 'feedback_type' | 'selection_session_id'>) =>
  row.feedback_type === 'service_review' && Boolean(row.selection_session_id);

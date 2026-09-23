import { ApiError } from './api.ts';

export type FeedbackDraft = {
  rating: number | null;
  tags: string[];
  note: string;
};

export type VisitFeedbackIntent = {
  draft: FeedbackDraft;
  idempotencyKey: string;
  attemptedSignature: string | null;
};

const emptyDraft = (): FeedbackDraft => ({ rating: null, tags: [], note: '' });
const defaultKeyFactory = () => crypto.randomUUID();

export function shouldEnterDirectFeedback(entry: { positionCode: string; source: string; qrToken: string }): boolean {
  void entry;
  return false;
}

function draftSignature(draft: FeedbackDraft) {
  return JSON.stringify(draft);
}

export function createVisitFeedbackIntent(keyFactory = defaultKeyFactory): VisitFeedbackIntent {
  return { draft: emptyDraft(), idempotencyKey: keyFactory(), attemptedSignature: null };
}

export function markVisitFeedbackAttempt(intent: VisitFeedbackIntent): VisitFeedbackIntent {
  return { ...intent, attemptedSignature: draftSignature(intent.draft) };
}

export function updateVisitFeedbackDraft(
  intent: VisitFeedbackIntent,
  draft: FeedbackDraft,
  keyFactory = defaultKeyFactory,
): VisitFeedbackIntent {
  const changedAfterAttempt = intent.attemptedSignature !== null
    && intent.attemptedSignature !== draftSignature(draft);
  return {
    draft,
    idempotencyKey: changedAfterAttempt ? keyFactory() : intent.idempotencyKey,
    attemptedSignature: changedAfterAttempt ? null : intent.attemptedSignature,
  };
}

export function visitFeedbackErrorMessage(error: unknown): string {
  const code = error instanceof ApiError
    ? error.code
    : typeof error === 'object' && error !== null && 'code' in error
      ? String(error.code)
      : '';
  if (code === 'FEEDBACK_RATE_LIMITED') return '提交得有点快，请稍后再试';
  if (code === 'FEEDBACK_TAG_INVALID') return '评价选项已更新，请重新选择后提交';
  if (code === 'IDEMPOTENCY_KEY_INVALID') return '提交信息已更新，请再次提交';
  if (code === 'VISIT_FEEDBACK_TOKEN_INVALID') return '本次到店信息已变化，请重新扫码后再提交';
  if (code === 'VISIT_FEEDBACK_TOKEN_EXPIRED') return '本次到店评价已过期，请重新扫码后再提交';
  if (code === 'IDEMPOTENCY_KEY_REUSED') return '评价内容已变化，请再次提交';
  if (code === 'SESSION_REPLACED') return '登录状态已变化，请重新登录或刷新后再试';
  if (typeof error === 'object' && error !== null && 'status' in error && Number(error.status) === 422) {
    return '请检查评分、标签数量和留言长度';
  }
  return error instanceof Error ? error.message : '评价暂未提交，请稍后再试';
}

export function shouldRenewVisitFeedbackToken(error: unknown): boolean {
  const code = error instanceof ApiError
    ? error.code
    : typeof error === 'object' && error !== null && 'code' in error
      ? String(error.code)
      : '';
  return code === 'VISIT_FEEDBACK_TOKEN_INVALID' || code === 'VISIT_FEEDBACK_TOKEN_EXPIRED';
}

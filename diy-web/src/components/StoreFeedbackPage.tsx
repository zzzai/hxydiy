import { Check, CheckCircle2, Star } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { createStoreVisitFeedbackEntry, submitVisitFeedback } from '../api';
import { canSubmitFeedback, feedbackRatingLabel, feedbackTagsForRating, MAX_FEEDBACK_TAGS } from '../customerCopy';
import { reportEntryUrl, serviceAccountEntry } from '../returnEntry';
import { createVisitFeedbackIntent, markVisitFeedbackAttempt, shouldRenewVisitFeedbackToken, updateVisitFeedbackDraft, visitFeedbackErrorMessage, type FeedbackDraft } from '../visitFeedback';

type StoreAccess = Awaited<ReturnType<typeof createStoreVisitFeedbackEntry>>;

function entryStoreId(): number | null {
  const value = new URLSearchParams(window.location.search).get('store') || '';
  const id = Number(value);
  return /^\d+$/.test(value) && Number.isSafeInteger(id) && id > 0 ? id : null;
}

export default function StoreFeedbackPage() {
  const [storeId] = useState(entryStoreId);
  const [access, setAccess] = useState<StoreAccess | null>(null);
  const [loading, setLoading] = useState(true);
  const [entryError, setEntryError] = useState('');
  const [error, setError] = useState('');
  const [intent, setIntent] = useState(() => createVisitFeedbackIntent());
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const busy = useRef(false);
  const entryRequest = useRef<Promise<StoreAccess> | null>(null);
  const { rating, tags, note } = intent.draft;

  async function requestAccess(): Promise<StoreAccess> {
    const result = await createStoreVisitFeedbackEntry(storeId!);
    if (result.store_id !== storeId || !result.visit_feedback_token) throw new Error('评价入口暂不可用');
    return result;
  }

  useEffect(() => {
    if (storeId === null) return;
    let active = true;
    const url = new URL('/', window.location.origin);
    url.searchParams.set('store', String(storeId));
    url.searchParams.set('view', 'feedback');
    window.history.replaceState(window.history.state, '', url.href);
    // Reuse the in-flight entry during StrictMode effect replay to avoid cookie races.
    entryRequest.current ||= requestAccess();
    void entryRequest.current.then((result) => {
      if (active) setAccess(result);
    }).catch(() => {
      if (active) setEntryError('暂时无法打开评价，请稍后重试');
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [storeId]);

  async function retryEntry() {
    if (busy.current || storeId === null) return;
    busy.current = true;
    setLoading(true);
    setEntryError('');
    try {
      setAccess(await requestAccess());
    } catch {
      setEntryError('暂时无法打开评价，请稍后重试');
    } finally {
      busy.current = false;
      setLoading(false);
    }
  }

  function updateDraft(draft: FeedbackDraft) {
    if (busy.current) return;
    setIntent((current) => updateVisitFeedbackDraft(current, draft));
    setError('');
  }

  async function submit() {
    if (busy.current || !access || submitted || !canSubmitFeedback(rating)) return;
    busy.current = true;
    setSubmitting(true);
    setError('');
    const attempted = markVisitFeedbackAttempt(intent);
    setIntent(attempted);
    const input = { rating, tags, note };
    try {
      let result;
      try {
        result = await submitVisitFeedback({ ...input, visit_feedback_token: access.visit_feedback_token }, attempted.idempotencyKey);
      } catch (failure) {
        if (!shouldRenewVisitFeedbackToken(failure)) throw failure;
        const renewed = await requestAccess();
        setAccess(renewed);
        // A single renewal keeps the same browser/store intent and never loops.
        result = await submitVisitFeedback({ ...input, visit_feedback_token: renewed.visit_feedback_token }, attempted.idempotencyKey);
      }
      if (!result.submitted) throw new Error('评价暂未提交，请稍后重试');
      setSubmitted(true);
    } catch (failure) {
      setError(shouldRenewVisitFeedbackToken(failure)
        ? '评价暂未提交，请稍后重试。已保留您填写的内容。'
        : failure instanceof TypeError ? '网络暂时不稳定，请重试。已保留您填写的内容。' : visitFeedbackErrorMessage(failure));
    } finally {
      busy.current = false;
      setSubmitting(false);
    }
  }

  return (
    <main className="store-feedback-page">
      <header className="store-feedback-brand"><strong>荷小悦</strong><span>{access?.store_name || '到店评价'}</span></header>
      {storeId === null ? <p role="alert" className="store-feedback-error">评价链接不完整，请重新扫描门店二维码</p> : !access ? (
        <div className="store-feedback-entry-state">
          {loading ? <p role="status">正在打开评价…</p> : <><p role="alert">{entryError}</p><button type="button" className="primary-action" onClick={() => void retryEntry()}>重试</button></>}
        </div>
      ) : submitted ? (
        <section className="store-feedback-success" aria-labelledby="store-feedback-success-title" role="status">
          <CheckCircle2 size={44} aria-hidden="true" />
          <h1 id="store-feedback-success-title">感谢您的评价</h1>
          <p>您的反馈已收到，我们会认真查看。</p>
          <div className="store-feedback-success-actions">
            <a className="primary-action" href={serviceAccountEntry(window.location.origin, storeId)}>返回菜单</a>
            <a className="secondary-action" href={reportEntryUrl(window.location.origin, storeId)}>查看检测报告</a>
          </div>
        </section>
      ) : (
        <section className="store-feedback-content" aria-labelledby="store-feedback-title" aria-busy={submitting}>
          <h1 id="store-feedback-title">这次体验怎么样？</h1>
          <p className="store-feedback-intro">选个评分，有建议也欢迎告诉我们。</p>
          <div className="store-feedback-rating">
            <div className="feedback-stars" role="group" aria-label="为本次到店体验评分">
              {[1, 2, 3, 4, 5].map((value) => <button key={value} type="button" aria-label={`${value}星`} aria-pressed={rating === value} className={rating !== null && value <= rating ? 'active' : ''} disabled={submitting} onClick={() => updateDraft({ ...intent.draft, rating: value, tags: [] })}><Star size={32} fill={rating !== null && value <= rating ? 'currentColor' : 'none'} aria-hidden="true" /></button>)}
            </div>
            <p className={`feedback-rating-label ${rating === null ? '' : 'selected'}`} aria-live="polite">{feedbackRatingLabel(rating)}</p>
          </div>
          {rating !== null && <div className="store-feedback-tag-section">
            <div className="feedback-tag-heading"><strong>{rating <= 2 ? '哪些地方没有达到预期？' : rating === 3 ? '哪些地方可以做得更好？' : '哪些地方让您满意？'}</strong><span>选填 · 最多3项</span></div>
            <div className="feedback-tags">{feedbackTagsForRating(rating).map((tag) => <button key={tag} type="button" aria-pressed={tags.includes(tag)} className={tags.includes(tag) ? 'selected' : ''} disabled={submitting} onClick={() => updateDraft({ ...intent.draft, tags: tags.includes(tag) ? tags.filter((item) => item !== tag) : tags.length < MAX_FEEDBACK_TAGS ? [...tags, tag] : tags })}>{tag}{tags.includes(tag) && <Check size={13} aria-hidden="true" />}</button>)}</div>
          </div>}
          <label className="store-feedback-note"><span>评价与建议 <small>选填</small></span><textarea value={note} maxLength={300} disabled={submitting} onChange={(event) => updateDraft({ ...intent.draft, note: event.target.value })} placeholder="说说您的感受，请勿填写手机号等隐私信息" /><small>{note.length}/300</small></label>
          {error && <p className="store-feedback-error" role="alert">{error}</p>}
          <button type="button" className="primary-action feedback-submit" disabled={submitting || !canSubmitFeedback(rating)} onClick={() => void submit()}>{submitting ? '正在提交…' : '提交评价'}</button>
        </section>
      )}
    </main>
  );
}

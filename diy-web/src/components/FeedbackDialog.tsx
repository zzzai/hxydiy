import { CheckCircle2, ChevronLeft, Star, X } from 'lucide-react';
import { useEffect, useState } from 'react';

import { canSubmitFeedback, feedbackRatingLabel, feedbackTagsForRating, isLowFeedbackRating, MAX_FEEDBACK_TAGS } from '../customerCopy';
import type { FeedbackDraft } from '../visitFeedback';

export default function FeedbackDialog({
  open,
  submitting,
  submitted,
  onClose,
  onSubmit,
  onViewRecord,
  onContinueShopping,
  title = '评价本次体验',
  lead = '这次服务体验如何？',
  successTitle = '感谢您的评价',
  successMessage = '已记录到本次到店服务。您的反馈会帮助我们持续改进体验。',
  continueLabel = '再次选购',
  value,
  onChange,
}: {
  open: boolean;
  submitting: boolean;
  submitted: boolean;
  onClose: () => void;
  onSubmit: (input: { rating: number; tags: string[]; note: string }) => void;
  onViewRecord?: () => void;
  onContinueShopping?: () => void;
  title?: string;
  lead?: string;
  successTitle?: string;
  successMessage?: string;
  continueLabel?: string;
  value?: FeedbackDraft;
  onChange?: (value: FeedbackDraft) => void;
}) {
  const [internalValue, setInternalValue] = useState<FeedbackDraft>({ rating: null, tags: [], note: '' });
  const currentValue = value || internalValue;
  const { rating, tags, note } = currentValue;
  const updateValue = (next: FeedbackDraft) => {
    if (submitting) return;
    if (!value) setInternalValue(next);
    onChange?.(next);
  };

  useEffect(() => {
    if (open && !submitted && !value) {
      setInternalValue({ rating: null, tags: [], note: '' });
    }
  }, [open, submitted, value]);

  if (!open) return null;

  const close = () => {
    if (!submitting) onClose();
  };

  const availableTags = feedbackTagsForRating(rating);
  const toggleTag = (tag: string) => {
    const nextTags = tags.includes(tag)
      ? tags.filter((item) => item !== tag)
      : tags.length >= MAX_FEEDBACK_TAGS ? tags : [...tags, tag];
    updateValue({ ...currentValue, tags: nextTags });
  };
  const selectRating = (value: number) => {
    updateValue({ ...currentValue, rating: value, tags: [] });
  };

  return (
    <div className="feedback-backdrop" role="presentation" onClick={close}>
      <section className="feedback-dialog" role="dialog" aria-modal="true" aria-labelledby="feedback-title" onClick={(event) => event.stopPropagation()}>
        <header className="feedback-header">
          <button type="button" className="icon-button" aria-label="返回" onClick={close} disabled={submitting}><ChevronLeft size={21} /></button>
          <strong id="feedback-title">{title}</strong>
          <button type="button" className="icon-button" aria-label="关闭" onClick={close} disabled={submitting}><X size={19} /></button>
        </header>
        {submitted ? (
          <div className="feedback-complete">
            <span><CheckCircle2 size={32} /></span>
            <h2>{successTitle}</h2>
            <p>{successMessage}</p>
            {onViewRecord || onContinueShopping ? <div className={`feedback-complete-actions ${onViewRecord && onContinueShopping ? '' : 'single'}`}>{onViewRecord && <button type="button" className="secondary-action" onClick={onViewRecord}>返回到店记录</button>}{onContinueShopping && <button type="button" className="primary-action" onClick={onContinueShopping}>{continueLabel}</button>}</div> : <button type="button" className="primary-action" onClick={onClose}>完成</button>}
          </div>
        ) : (
          <div className="feedback-form">
            <p className="feedback-lead">{lead}</p>
            <p className={`feedback-rating-label ${rating === null ? '' : 'selected'}`}>{feedbackRatingLabel(rating)}</p>
            <div className="feedback-stars" aria-label={rating === null ? '尚未评分' : `${rating}星评价`}>
              {[1, 2, 3, 4, 5].map((value) => (
                <button key={value} type="button" aria-label={`${value}星`} aria-pressed={rating === value} className={rating !== null && value <= rating ? 'active' : ''} disabled={submitting} onClick={() => selectRating(value)}>
                  <Star size={30} fill="currentColor" />
                </button>
              ))}
            </div>
            {rating !== null && <><div className="feedback-tag-heading"><strong>{isLowFeedbackRating(rating) ? '哪些地方没有达到预期？' : rating === 3 ? '哪些地方可以做得更好？' : '哪些地方让您满意？'}</strong><span>可多选，最多3项</span></div><div className="feedback-tags">{availableTags.map((tag) => <button key={tag} type="button" className={tags.includes(tag) ? 'selected' : ''} disabled={submitting} onClick={() => toggleTag(tag)}>{tag}</button>)}</div></>}
            {isLowFeedbackRating(rating) && <p className="feedback-follow-up-note">如需处理本次体验问题，请在到店后联系门店工作人员；顾客端暂不承诺自动回访。</p>}
            <label className="feedback-note"><span>还有想告诉我们的吗？（选填）</span><textarea value={note} maxLength={300} disabled={submitting} onChange={(event) => updateValue({ ...currentValue, note: event.target.value })} placeholder="请勿填写手机号或其他隐私信息" /><small>{note.length}/300</small></label>
            <button type="button" className="primary-action feedback-submit" disabled={submitting || !canSubmitFeedback(rating)} onClick={() => { if (canSubmitFeedback(rating)) onSubmit({ rating, tags, note }); }}>{submitting ? '正在提交' : '提交评价'}</button>
          </div>
        )}
      </section>
    </div>
  );
}

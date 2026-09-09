import { CheckCircle2, ChevronLeft, Star, X } from 'lucide-react';
import { useEffect, useState } from 'react';

import { canSubmitFeedback, feedbackRatingLabel, feedbackTagsForRating, isLowFeedbackRating, MAX_FEEDBACK_TAGS } from '../customerCopy';

export default function FeedbackDialog({
  open,
  submitting,
  submitted,
  onClose,
  onSubmit,
  onViewRecord,
  onContinueShopping,
}: {
  open: boolean;
  submitting: boolean;
  submitted: boolean;
  onClose: () => void;
  onSubmit: (input: { rating: number; tags: string[]; note: string }) => void;
  onViewRecord?: () => void;
  onContinueShopping?: () => void;
}) {
  const [rating, setRating] = useState<number | null>(null);
  const [tags, setTags] = useState<string[]>([]);
  const [note, setNote] = useState('');

  useEffect(() => {
    if (open && !submitted) {
      setRating(null);
      setTags([]);
      setNote('');
    }
  }, [open, submitted]);

  if (!open) return null;

  const availableTags = feedbackTagsForRating(rating);
  const toggleTag = (tag: string) => {
    setTags((current) => {
      if (current.includes(tag)) return current.filter((item) => item !== tag);
      return current.length >= MAX_FEEDBACK_TAGS ? current : [...current, tag];
    });
  };
  const selectRating = (value: number) => {
    setRating(value);
    setTags([]);
  };

  return (
    <div className="feedback-backdrop" role="presentation" onClick={onClose}>
      <section className="feedback-dialog" role="dialog" aria-modal="true" aria-labelledby="feedback-title" onClick={(event) => event.stopPropagation()}>
        <header className="feedback-header">
          <button type="button" className="icon-button" aria-label="返回" onClick={onClose}><ChevronLeft size={21} /></button>
          <strong id="feedback-title">评价本次体验</strong>
          <button type="button" className="icon-button" aria-label="关闭" onClick={onClose}><X size={19} /></button>
        </header>
        {submitted ? (
          <div className="feedback-complete">
            <span><CheckCircle2 size={32} /></span>
            <h2>感谢您的评价</h2>
            <p>已记录到本次到店服务。您的反馈会帮助我们持续改进体验。</p>
            {onViewRecord || onContinueShopping ? <div className="feedback-complete-actions">{onViewRecord && <button type="button" className="secondary-action" onClick={onViewRecord}>返回到店记录</button>}{onContinueShopping && <button type="button" className="primary-action" onClick={onContinueShopping}>再次选购</button>}</div> : <button type="button" className="primary-action" onClick={onClose}>完成</button>}
          </div>
        ) : (
          <div className="feedback-form">
            <p className="feedback-lead">这次服务体验如何？</p>
            <p className={`feedback-rating-label ${rating === null ? '' : 'selected'}`}>{feedbackRatingLabel(rating)}</p>
            <div className="feedback-stars" aria-label={rating === null ? '尚未评分' : `${rating}星评价`}>
              {[1, 2, 3, 4, 5].map((value) => (
                <button key={value} type="button" aria-label={`${value}星`} aria-pressed={rating === value} className={rating !== null && value <= rating ? 'active' : ''} onClick={() => selectRating(value)}>
                  <Star size={30} fill="currentColor" />
                </button>
              ))}
            </div>
            {rating !== null && <><div className="feedback-tag-heading"><strong>{isLowFeedbackRating(rating) ? '哪些地方没有达到预期？' : rating === 3 ? '哪些地方可以做得更好？' : '哪些地方让您满意？'}</strong><span>可多选，最多3项</span></div><div className="feedback-tags">{availableTags.map((tag) => <button key={tag} type="button" className={tags.includes(tag) ? 'selected' : ''} onClick={() => toggleTag(tag)}>{tag}</button>)}</div></>}
            {isLowFeedbackRating(rating) && <p className="feedback-follow-up-note">如需处理本次体验问题，请在到店后联系门店工作人员；顾客端暂不承诺自动回访。</p>}
            <label className="feedback-note"><span>还有想告诉我们的吗？（选填）</span><textarea value={note} maxLength={300} onChange={(event) => setNote(event.target.value)} placeholder="请勿填写手机号或其他隐私信息" /><small>{note.length}/300</small></label>
            <button type="button" className="primary-action feedback-submit" disabled={submitting || !canSubmitFeedback(rating)} onClick={() => { if (canSubmitFeedback(rating)) onSubmit({ rating, tags, note }); }}>{submitting ? '正在提交' : '提交评价'}</button>
          </div>
        )}
      </section>
    </div>
  );
}

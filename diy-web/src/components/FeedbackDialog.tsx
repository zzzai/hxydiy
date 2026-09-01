import { CheckCircle2, ChevronLeft, Star, X } from 'lucide-react';
import { useEffect, useState } from 'react';

import { FEEDBACK_TAGS } from '../customerCopy';

export default function FeedbackDialog({
  open,
  submitting,
  submitted,
  onClose,
  onSubmit,
}: {
  open: boolean;
  submitting: boolean;
  submitted: boolean;
  onClose: () => void;
  onSubmit: (input: { rating: number; tags: string[]; note: string }) => void;
}) {
  const [rating, setRating] = useState(5);
  const [tags, setTags] = useState<string[]>([]);
  const [note, setNote] = useState('');

  useEffect(() => {
    if (open && !submitted) {
      setRating(5);
      setTags([]);
      setNote('');
    }
  }, [open, submitted]);

  if (!open) return null;

  const toggleTag = (tag: string) => {
    setTags((current) => current.includes(tag) ? current.filter((item) => item !== tag) : [...current, tag]);
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
            <p>您的反馈会帮助我们把每一次服务做得更好。</p>
            <button type="button" className="primary-action" onClick={onClose}>完成</button>
          </div>
        ) : (
          <div className="feedback-form">
            <p className="feedback-lead">这次服务体验如何？</p>
            <div className="feedback-stars" aria-label={`${rating}星评价`}>
              {[1, 2, 3, 4, 5].map((value) => (
                <button key={value} type="button" aria-label={`${value}星`} className={value <= rating ? 'active' : ''} onClick={() => setRating(value)}>
                  <Star size={30} fill="currentColor" />
                </button>
              ))}
            </div>
            <div className="feedback-tags">
              {FEEDBACK_TAGS.map((tag) => <button key={tag} type="button" className={tags.includes(tag) ? 'selected' : ''} onClick={() => toggleTag(tag)}>{tag}</button>)}
            </div>
            <textarea value={note} maxLength={1000} onChange={(event) => setNote(event.target.value)} placeholder="还有想告诉我们的吗？（选填）" />
            <button type="button" className="primary-action feedback-submit" disabled={submitting} onClick={() => onSubmit({ rating, tags, note })}>{submitting ? '正在提交' : '提交评价'}</button>
          </div>
        )}
      </section>
    </div>
  );
}

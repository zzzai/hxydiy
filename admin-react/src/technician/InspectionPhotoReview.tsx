import type { InspectionPhoto, InspectionVerdict } from '../api';

const labels: Record<InspectionVerdict, string> = { pass: '通过', fix: '需整改', retake: '需补拍' };

export default function InspectionPhotoReview({ photo, enabled }: { photo: InspectionPhoto; enabled: boolean }) {
  const review = photo.review;
  if (!photo.reviewable || (!enabled && !review)) return null;
  const result = review?.result;
  return <div className="inspection-review">
    <div aria-live="polite">
      {result ? <><strong className={'inspection-verdict ' + result.verdict}>AI 审核 · {labels[result.verdict]}</strong>
        <p>{result.location} · {result.evidence}</p>
        {result.verdict !== 'pass' && <p className="inspection-next-action">{result.action}</p>}</>
        : <span className="inspection-review-status">{!enabled ? '自动审核已暂停'
          : review?.state === 'failed' ? (review.retry_scheduled ? '稍后自动重试' : 'AI 未能给出结论')
          : review?.state === 'running' ? 'AI 正在审核' : '等待自动审核'}</span>}
      {review?.manual_verdict && <strong className="inspection-manual">历史人工结论 · {labels[review.manual_verdict]}</strong>}
    </div>
  </div>;
}

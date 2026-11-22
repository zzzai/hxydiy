import { useRef, useState } from 'react';
import { message } from 'antd';
import { confirmInspectionReview, type InspectionPhoto, type InspectionVerdict } from '../api';
import { requestErrorMessage } from '../requestError';

const labels: Record<InspectionVerdict, string> = { pass: '通过', fix: '需整改', retake: '需补拍' };

export default function InspectionPhotoReview({ photo, enabled, disabled, onRefresh }: {
  photo: InspectionPhoto; enabled: boolean; disabled: boolean; onRefresh: () => Promise<void>;
}) {
  const [deciding, setDeciding] = useState(false);
  const [verdict, setVerdict] = useState<InspectionVerdict | ''>('');
  const [saving, setSaving] = useState(false);
  const lock = useRef(false);
  const review = photo.review;
  if (!photo.reviewable || (!enabled && !review)) return null;
  const result = review?.result;
  const finished = review?.state === 'done';
  const blocked = disabled || saving;

  const save = async (decision: InspectionVerdict) => {
    if (lock.current || disabled) return;
    lock.current = true; setSaving(true);
    try {
      await confirmInspectionReview(photo, decision);
      setDeciding(false);
    } catch (error) { message.error(requestErrorMessage(error)); }
    finally {
      try { await onRefresh(); } finally { lock.current = false; setSaving(false); }
    }
  };

  return <div className="inspection-review">
    <div aria-live="polite">
      {result ? <><strong className={'inspection-verdict ' + result.verdict}>AI 审核 · {labels[result.verdict]}</strong>
        <p>{result.location} · {result.evidence}</p>
        {result.verdict !== 'pass' && <p className="inspection-next-action">{result.action}</p>}</>
        : <span className="inspection-review-status">{!enabled ? '自动审核已暂停'
          : review?.state === 'failed' ? (review.retry_scheduled ? '稍后自动重试' : 'AI 未能给出结论')
          : review?.state === 'running' ? 'AI 正在审核' : '等待自动审核'}</span>}
      {review?.manual_verdict && <strong className="inspection-manual">店长更正 · {labels[review.manual_verdict]}</strong>}
    </div>
    {finished && !review?.manual_verdict && <div className="inspection-review-actions">
      {!deciding && <button type="button" disabled={blocked} onClick={() => setDeciding(true)}>结果有误</button>}
      {deciding && <>
        <select aria-label="更正结论" disabled={blocked} value={verdict}
          onChange={event => setVerdict(event.target.value as InspectionVerdict | '')}>
          <option value="">选择更正结论</option>
          <option value="pass">通过</option><option value="fix">需整改</option><option value="retake">需补拍</option>
        </select>
        <button type="button" disabled={blocked || !verdict} onClick={() => verdict && void save(verdict)}>保存更正</button>
        <button type="button" disabled={blocked} onClick={() => setDeciding(false)}>取消</button>
      </>}
    </div>}
  </div>;
}

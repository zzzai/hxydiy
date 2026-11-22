import { useRef, useState } from 'react';
import { message } from 'antd';
import { confirmInspectionReview, requestInspectionReview, type InspectionPhoto, type InspectionVerdict } from '../api';
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
  const finished = review?.state === 'done' || review?.state === 'failed';
  const requestable = !review || review.state === 'failed' || review.state === 'superseded';
  const blocked = disabled || saving;

  const save = async (decision?: InspectionVerdict) => {
    if (lock.current || disabled) return;
    lock.current = true; setSaving(true);
    try {
      if (decision) await confirmInspectionReview(photo, decision);
      else await requestInspectionReview(photo);
      setDeciding(false);
    } catch (error) { message.error(requestErrorMessage(error)); }
    finally {
      try { await onRefresh(); } finally { lock.current = false; setSaving(false); }
    }
  };

  return <div className="inspection-review">
    <div aria-live="polite">
      {result ? <><strong className={'inspection-verdict ' + result.verdict}>AI 初审 · {labels[result.verdict]}</strong>
        <p>{result.location} · {result.evidence}</p>
        {result.verdict !== 'pass' && <p className="inspection-next-action">{result.action}</p>}</>
        : <span className="inspection-review-status">{!review || review.state === 'superseded' ? '尚未送审'
          : review.state === 'failed' ? 'AI 初审未完成' : !enabled ? 'AI 初审已暂停'
          : review.state === 'running' ? 'AI 正在审核' : '等待 AI 初审'}</span>}
      {review?.manual_verdict && <strong className="inspection-manual">店长复核 · {labels[review.manual_verdict]}</strong>}
    </div>
    {!review?.manual_verdict && <div className="inspection-review-actions">
      {enabled && requestable && <button type="button" disabled={blocked} onClick={() => void save()}>
        {review?.state === 'failed' ? '重试初审' : '审核这张照片'}</button>}
      {finished && !deciding && <button type="button" disabled={blocked} onClick={() => setDeciding(true)}>店长复核</button>}
      {finished && deciding && <>
        <select aria-label="店长复核结论" disabled={blocked} value={verdict}
          onChange={event => setVerdict(event.target.value as InspectionVerdict | '')}>
          <option value="">选择复核结论</option>
          <option value="pass">通过</option><option value="fix">需整改</option><option value="retake">需补拍</option>
        </select>
        <button type="button" disabled={blocked || !verdict} onClick={() => verdict && void save(verdict)}>确认复核</button>
        <button type="button" disabled={blocked} onClick={() => setDeciding(false)}>取消</button>
      </>}
    </div>}
  </div>;
}

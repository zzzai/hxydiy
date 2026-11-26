import { useState } from 'react';
import { Button, Spin, message } from 'antd';
import { AudioOutlined, RightOutlined } from '@ant-design/icons';
import { getManagerDaily, submitManagerDaily, type InspectionArea } from '../api';
import ManagerAreaPhotos from './ManagerAreaPhotos';
import InspectionHistory from './InspectionHistory';

type Daily = Awaited<ReturnType<typeof getManagerDaily>>['data'];
export default function ManagerDailyOpsView({ daily, loading, onRefresh, onOpenRecordings }: {
  daily: Daily | null; loading: boolean; onRefresh: () => Promise<void>; onOpenRecordings: () => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (submitting || uploading) return;
    setSubmitting(true);
    try {
      await submitManagerDaily();
      await onRefresh();
      message.success('今日巡检已提交');
    } catch (failure) {
      const detail = (failure as { response?: { data?: { detail?: { message?: string } } } })?.response?.data?.detail;
      message.error(detail?.message || '请先完成各区域照片和晨会录音');
    } finally { setSubmitting(false); }
  };

  if (loading && !daily) return <div className="manager-p0-loading"><Spin /> 正在加载今日经营…</div>;
  if (!daily) return <div className="manager-p0-loading">今日经营暂时不可用</div>;

  const done = daily.completion.areas_done;
  const total = daily.completion.areas_total;
  const remaining = (daily.areas as InspectionArea[]).filter(area => !area.done);
  const canSubmit = total > 0 && done === total && !uploading && !submitting && daily.completion.has_meeting && daily.status !== 'submitted';
  return <div className="manager-p0-stack inspection-workspace">
    <section className="inspection-summary manager-p0-progress-card">
      <div className="inspection-progress-label"><h2>拍摄进度</h2><strong>{done}<small> / {total}</small></strong></div>
      <progress className="inspection-progress" value={done} max={total || 1} aria-label="已完成拍摄点" />
      {remaining.length > 0 && remaining.length <= 3 && <p className="inspection-camera-note">
        待拍：{remaining.map(area => area.group === 'spa_rooms' ? 'SPA 房·' + area.label : area.label).join('、')}
      </p>}
      <button type="button" className="inspection-meeting" onClick={onOpenRecordings}>
        <span><AudioOutlined />晨会录音</span><span>{daily.completion.has_meeting ? '查看录音' : '去录音'}<RightOutlined /></span>
      </button>
    </section>

    <ManagerAreaPhotos areas={daily.areas} reviewEnabled={daily.inspection_ai_enabled === true} limit={daily.max_photos_per_area} businessDate={daily.business_date}
      submitted={daily.status === 'submitted'} disabled={submitting || uploading} onBusy={setUploading} onRefresh={onRefresh} />

    <section className="inspection-submit">
      <Button type="primary" size="large" block disabled={!canSubmit} loading={submitting} onClick={() => void submit()}>
        {daily.status === 'submitted' ? '今日巡检已提交' : '提交今日巡检'}
      </Button>
      {!canSubmit && daily.status !== 'submitted' && !uploading && !submitting && <p>{[
        remaining.length ? '还有 ' + remaining.length + ' 个拍摄点待拍' : '',
        daily.completion.has_meeting ? '' : '晨会录音待上传',
      ].filter(Boolean).join('，')}</p>}
    </section>
    <InspectionHistory key={daily.business_date} today={daily.business_date} />
  </div>;
}

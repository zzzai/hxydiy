import { useState } from 'react';
import { Button, Spin, Tag, message } from 'antd';
import { AudioOutlined, ReloadOutlined } from '@ant-design/icons';
import { getManagerDaily, submitManagerDaily } from '../api';
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
  const canSubmit = total > 0 && done === total && !uploading && !submitting && daily.completion.has_meeting && daily.status !== 'submitted';
  return <div className="manager-p0-stack">
    <section className="manager-p0-card manager-p0-progress-card">
      <div className="manager-p0-card-head"><div><small>今日经营</small><h2>{done}/{total} 区域</h2></div><Tag color={daily.status === 'submitted' ? 'green' : 'gold'}>{daily.status === 'submitted' ? '已提交' : '进行中'}</Tag></div>
      <div className="manager-p0-progress"><i style={{ width: `${total ? done / total * 100 : 0}%` }} /></div>
      <div className="manager-p0-actions-inline"><span>{daily.completion.has_meeting ? '晨会已录音' : '晨会待录音'}</span><Button size="small" icon={<AudioOutlined />} onClick={onOpenRecordings}>{daily.completion.has_meeting ? '查看录音' : '去录音'}</Button></div>
    </section>

    <ManagerAreaPhotos areas={daily.areas} reviewEnabled={daily.inspection_ai_enabled === true} limit={daily.max_photos_per_area} businessDate={daily.business_date}
      submitted={daily.status === 'submitted'} disabled={submitting || uploading} onBusy={setUploading} onRefresh={onRefresh} />

    <InspectionHistory key={daily.business_date} today={daily.business_date} />

    <Button type="primary" size="large" block disabled={!canSubmit} loading={submitting} onClick={() => void submit()}>{daily.status === 'submitted' ? '今日已提交' : canSubmit ? '提交今日巡检' : '拍齐各区照片并上传晨会录音后可提交'}</Button>
    <button type="button" className="manager-p0-text-link" onClick={() => void onRefresh()}><ReloadOutlined /> 刷新今日记录</button>
  </div>;
}

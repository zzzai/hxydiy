import { useEffect, useRef, useState } from 'react';
import { Button, Spin, Tag, message } from 'antd';
import { AudioOutlined, ReloadOutlined, ScanOutlined, StarOutlined, StopOutlined, GiftOutlined } from '@ant-design/icons';
import { getManagerDaily, retryManagerMeetingTranscription, saveManagerMeeting, submitManagerDaily, uploadMedia } from '../api';
import ManagerAreaPhotos from './ManagerAreaPhotos';
import { WavRecorder } from './wavRecorder';

type Daily = Awaited<ReturnType<typeof getManagerDaily>>['data'];
function timeText(value?: string) {
  if (!value) return '';
  return new Date(value).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
}

function MeetingPanel({ daily, onRefresh }: { daily: Daily; onRefresh: () => Promise<void> }) {
  const recorder = useRef<WavRecorder | null>(null);
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [busy, setBusy] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const timer = useRef<number | null>(null);
  const meeting = daily.meetings[0];

  useEffect(() => () => {
    if (timer.current) window.clearInterval(timer.current);
    const active = recorder.current;
    recorder.current = null;
    if (active) void active.stop().catch(() => undefined);
  }, []);

  const start = async () => {
    try {
      const instance = new WavRecorder();
      await instance.start();
      recorder.current = instance;
      setRecording(true); setSeconds(0);
      timer.current = window.setInterval(() => setSeconds((value) => value + 1), 1000);
    } catch {
      message.error('无法使用麦克风，请检查浏览器权限');
    }
  };

  const stop = async () => {
    if (!recorder.current) return;
    if (timer.current) window.clearInterval(timer.current);
    setRecording(false); setBusy(true);
    try {
      const result = await recorder.current.stop();
      recorder.current = null;
      const uploaded = await uploadMedia(new File([result.blob], 'meeting.wav', { type: 'audio/wav' }), 'meeting_audio');
      await saveManagerMeeting({ media_id: uploaded.data.id, duration_seconds: result.duration, title: '晨会' });
      await onRefresh();
      message.success('晨会录音已上传');
    } catch (failure) {
      const detail = (failure as { response?: { data?: { detail?: string | { message?: string } } } })?.response?.data?.detail;
      message.error(typeof detail === 'string' ? detail : detail?.message || '录音上传失败');
    } finally {
      setBusy(false); setSeconds(0);
    }
  };

  const retry = async () => {
    if (!meeting || retrying) return;
    setRetrying(true);
    try {
      await retryManagerMeetingTranscription(meeting.id);
      await onRefresh();
      message.success('已重新提交转写');
    } catch (failure) {
      const detail = (failure as { response?: { data?: { detail?: { message?: string } } } })?.response?.data?.detail;
      message.error(detail?.message || '无法重新转写');
    } finally { setRetrying(false); }
  };

  return <section className="manager-p0-card">
    <div className="manager-p0-card-head"><div><small>每日会议</small><h3>晨会录音</h3></div>{meeting && <Tag color={meeting.transcript_status === 'transcribed' ? 'green' : meeting.transcript_status === 'failed' ? 'red' : 'gold'}>{meeting.transcript_status === 'transcribed' ? '已转写' : meeting.transcript_status === 'failed' ? '转写失败' : meeting.transcript_status === 'not_configured' ? '待配置转写' : '转写中'}</Tag>}</div>
    {recording ? <div className="manager-p0-recording"><span className="manager-p0-recording-dot" /><strong>{Math.floor(seconds / 60).toString().padStart(2, '0')}:{(seconds % 60).toString().padStart(2, '0')}</strong><Button danger icon={<StopOutlined />} onClick={() => void stop()}>停止并上传</Button></div>
      : <div className="manager-p0-meeting-row"><div className="manager-p0-mic"><AudioOutlined /></div><div><strong>{meeting ? meeting.title : '今天还没有录音'}</strong><small>{meeting ? `${timeText(meeting.created_at)} · ${Math.floor(meeting.duration_seconds / 60)} 分 ${meeting.duration_seconds % 60} 秒` : '点击开始，录完自动上传'}</small></div>{meeting ? <Button size="small" onClick={() => void start()}>重录</Button> : <Button type="primary" icon={<AudioOutlined />} loading={busy} onClick={() => void start()}>开始录音</Button>}</div>}
    {busy && <p className="manager-p0-muted"><Spin size="small" /> 正在上传录音…</p>}
    {meeting && <>
      {meeting.media?.url && <audio className="manager-p0-audio" controls preload="none" src={meeting.media.url} />}
      {meeting.transcript_status === 'transcribed' && meeting.transcript_text && <div className="manager-p0-transcript"><strong>转写</strong><p>{meeting.transcript_text}</p></div>}
      {meeting.transcript_status === 'not_configured' && <p className="manager-p0-muted">录音已保存；总部配置腾讯云 ASR 密钥后即可转写。</p>}
      {meeting.transcript_status === 'failed' && <p className="manager-p0-error">{meeting.error_message || '转写失败'}<Button size="small" loading={retrying} onClick={() => void retry()}>重试</Button></p>}
      <p className="manager-p0-fine">音频、文字稿保留 90 天，到期自动清理。</p>
    </>}
  </section>;
}

export default function ManagerDailyOpsView({ daily, loading, onRefresh, onOpenReviews, onOpenCoupons, onOpenRedeemCoupon, onOpenCouponHistory }: {
  daily: Daily | null; loading: boolean; onRefresh: () => Promise<void>; onOpenReviews: () => void; onOpenCoupons: () => void; onOpenRedeemCoupon: () => void; onOpenCouponHistory: () => void;
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
      <p className="manager-p0-muted">照片、晨会、评价、发券都在这里留痕；照片和录音保留 90 天。</p>
      <div className="manager-p0-actions-inline"><Button size="small" icon={<StarOutlined />} onClick={onOpenReviews}>看评价</Button><Button size="small" icon={<GiftOutlined />} onClick={onOpenCoupons}>发券</Button><Button size="small" icon={<ScanOutlined />} onClick={onOpenRedeemCoupon}>核销券</Button><Button size="small" onClick={onOpenCouponHistory}>券记录</Button></div>
    </section>

    <ManagerAreaPhotos areas={daily.areas} limit={daily.max_photos_per_area} businessDate={daily.business_date}
      submitted={daily.status === 'submitted'} disabled={submitting || uploading} onBusy={setUploading} onRefresh={onRefresh} />

    <MeetingPanel daily={daily} onRefresh={onRefresh} />

    <Button type="primary" size="large" block disabled={!canSubmit} loading={submitting} onClick={() => void submit()}>{daily.status === 'submitted' ? '今日已提交' : canSubmit ? '提交今日巡检' : '拍齐各区照片并上传晨会录音后可提交'}</Button>
    <button type="button" className="manager-p0-text-link" onClick={() => void onRefresh()}><ReloadOutlined /> 刷新今日记录</button>
  </div>;
}

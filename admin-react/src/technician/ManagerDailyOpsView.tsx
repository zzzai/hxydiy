import { useRef, useState } from 'react';
import { Button, Input, Spin, Tag, message } from 'antd';
import { AudioOutlined, CameraOutlined, CheckCircleFilled, ReloadOutlined, StarOutlined, StopOutlined, GiftOutlined } from '@ant-design/icons';
import { getManagerDaily, retryManagerMeetingTranscription, saveManagerAreaPhoto, saveManagerMeeting, submitManagerDaily, uploadMedia } from '../api';
import { WavRecorder } from './wavRecorder';

type Daily = Awaited<ReturnType<typeof getManagerDaily>>['data'];
type Area = Daily['areas'][number];

const AREA_ICONS: Record<string, string> = {
  restroom: '卫', water_room: '水', cashier: '收', rest_area: '休', foot_area: '足',
};

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

export default function ManagerDailyOpsView({ daily, loading, onRefresh, onOpenReviews, onOpenCoupons }: {
  daily: Daily | null; loading: boolean; onRefresh: () => Promise<void>; onOpenReviews: () => void; onOpenCoupons: () => void;
}) {
  const [uploading, setUploading] = useState('');
  const inputs = useRef<Record<string, HTMLInputElement | null>>({});

  const uploadPhoto = async (area: Area, file?: File) => {
    if (!file) return;
    setUploading(area.key);
    try {
      const media = await uploadMedia(file, 'daily_area');
      await saveManagerAreaPhoto({ area: area.key, media_id: media.data.id });
      await onRefresh();
      message.success(`${area.label}照片已上传`);
    } catch (failure) {
      const detail = (failure as { response?: { data?: { detail?: string | { message?: string } } } })?.response?.data?.detail;
      message.error(typeof detail === 'string' ? detail : detail?.message || '照片上传失败');
    } finally { setUploading(''); }
  };

  const submit = async () => {
    try {
      await submitManagerDaily();
      await onRefresh();
      message.success('今日巡检已提交');
    } catch (failure) {
      const detail = (failure as { response?: { data?: { detail?: { message?: string } } } })?.response?.data?.detail;
      message.error(detail?.message || '请先完成 5 个区域照片和晨会录音');
    }
  };

  if (loading && !daily) return <div className="manager-p0-loading"><Spin /> 正在加载今日经营…</div>;
  if (!daily) return <div className="manager-p0-loading">今日经营暂时不可用</div>;

  const done = daily.completion.areas_done;
  const canSubmit = done === 5 && daily.completion.has_meeting && daily.status !== 'submitted';
  return <div className="manager-p0-stack">
    <section className="manager-p0-card manager-p0-progress-card">
      <div className="manager-p0-card-head"><div><small>今日经营</small><h2>{done}/5 区域</h2></div><Tag color={daily.status === 'submitted' ? 'green' : 'gold'}>{daily.status === 'submitted' ? '已提交' : '进行中'}</Tag></div>
      <div className="manager-p0-progress"><i style={{ width: `${(done / 5) * 100}%` }} /></div>
      <p className="manager-p0-muted">照片、晨会、评价、发券都在这里留痕；照片和录音保留 90 天。</p>
      <div className="manager-p0-actions-inline"><Button size="small" icon={<StarOutlined />} onClick={onOpenReviews}>看评价</Button><Button size="small" icon={<GiftOutlined />} onClick={onOpenCoupons}>发券</Button></div>
    </section>

    <section className="manager-p0-card">
      <div className="manager-p0-card-head"><div><small>必做</small><h3>区域照片</h3></div><span className="manager-p0-muted">{done}/5</span></div>
      <div className="manager-p0-area-grid">
        {daily.areas.map((area: Area) => <button type="button" key={area.key} className={'manager-p0-area' + (area.done ? ' is-done' : '')} disabled={uploading === area.key} onClick={() => inputs.current[area.key]?.click()}>
          {area.photo?.media?.url ? <img src={area.photo.media.url} alt={area.label} /> : <span className="manager-p0-area-placeholder">{AREA_ICONS[area.key] || '区'}</span>}
          <span className="manager-p0-area-name">{area.label}</span>
          <span className="manager-p0-area-state">{uploading === area.key ? '上传中…' : area.done ? `${timeText(area.photo?.captured_at)} 已上传` : '点击拍照'}</span>
          {area.done && <CheckCircleFilled className="manager-p0-area-check" />}
          <input ref={(node) => { inputs.current[area.key] = node; }} type="file" accept="image/*" capture="environment" hidden onChange={(event) => void uploadPhoto(area, event.target.files?.[0])} />
        </button>)}
      </div>
    </section>

    <MeetingPanel daily={daily} onRefresh={onRefresh} />

    <Button type="primary" size="large" block disabled={!canSubmit} onClick={() => void submit()}>{daily.status === 'submitted' ? '今日已提交' : canSubmit ? '提交今日巡检' : '完成 5 区域照片和晨会录音后可提交'}</Button>
    <button type="button" className="manager-p0-text-link" onClick={() => void onRefresh()}><ReloadOutlined /> 刷新今日记录</button>
  </div>;
}

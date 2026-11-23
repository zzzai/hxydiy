import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Spin } from 'antd';
import { ArrowLeftOutlined, AudioOutlined, StopOutlined } from '@ant-design/icons';
import { useLocation, useNavigate } from 'react-router-dom';
import { client, getManagerDaily, retryManagerMeetingTranscription, saveManagerMeeting, uploadMedia } from '../api';
import { useTechnicianSession } from './useTechnicianSession';
import { WavRecorder } from './wavRecorder';
import './manager-p0.css';

type Media = { id: number; url: string };
type Meeting = { id: number; title: string; duration_seconds: number; created_at: string; media: Media | null;
  transcript_status: string; transcript_text: string; error_message: string };
type Day = { business_date: string; meetings: Meeting[] };
type Clip = { file: File; duration: number; businessDate: string; mediaId?: number };

function duration(seconds: number) {
  return [Math.floor(seconds / 60), seconds % 60].map(value => String(value).padStart(2, '0')).join(':');
}

function Playback({ media }: { media: Media }) {
  const current = useTechnicianSession();
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);
  if (media.url !== `/api/v1/admin/media/${media.id}/content` || url) {
    return <audio aria-label="录音回放" className="manager-p0-audio" controls preload="none" src={url || media.url} />;
  }
  const load = async () => {
    setLoading(true); setError(false);
    try {
      const response = await client.get<Blob>(`/admin/media/${media.id}/content`, { responseType: 'blob' });
      if (current()) setUrl(URL.createObjectURL(response.data));
    } catch { if (current()) setError(true); }
    finally { if (current()) setLoading(false); }
  };
  return <div><Button loading={loading} onClick={() => void load()}>载入录音</Button>{error && <p role="alert">未能载入录音，请重试。</p>}</div>;
}

function SavedMeeting({ meeting, refresh }: { meeting: Meeting; refresh: () => Promise<void> }) {
  const current = useTechnicianSession();
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState('');
  const retry = async () => {
    setRetrying(true); setError('');
    try {
      await retryManagerMeetingTranscription(meeting.id);
      if (current()) await refresh();
    } catch { if (current()) setError('重新转写失败，请稍后重试。'); }
    finally { if (current()) setRetrying(false); }
  };
  return <article className="manager-recording-item">
    <h3>{meeting.title || '晨会'}</h3>
    <small>{new Date(meeting.created_at).toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', hour12: false })} · {duration(meeting.duration_seconds)}</small>
    {meeting.media ? <Playback key={meeting.media.id} media={meeting.media} /> : <p>音频已不可用</p>}
    {meeting.transcript_status === 'transcribed' && meeting.transcript_text && <details className="manager-p0-transcript"><summary>查看文字稿</summary><p>{meeting.transcript_text}</p></details>}
    {meeting.transcript_status === 'transcribing' && <p role="status">正在转写</p>}
    {meeting.transcript_status === 'not_configured' && <p className="manager-p0-muted">录音已保存，门店暂未启用转写。</p>}
    {meeting.transcript_status === 'failed' && <div><span>转写失败 </span><Button size="small" loading={retrying} onClick={() => void retry()}>重新转写</Button></div>}
    {error && <p role="alert">{error}</p>}
  </article>;
}

export default function ManagerRecordingsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const current = useTechnicianSession();
  const [date, setDate] = useState('');
  const [today, setToday] = useState('');
  const [day, setDay] = useState<Day | null>(null);
  const [readError, setReadError] = useState(false);
  const readVersion = useRef(0);
  const [phase, setPhase] = useState<'idle' | 'opening' | 'recording' | 'saving'>('idle');
  const [seconds, setSeconds] = useState(0);
  const [note, setNote] = useState('');
  const [clip, setClip] = useState<Clip | null>(null);
  const recording = useRef<WavRecorder | null>(null);
  const saving = useRef(false);

  const refresh = useCallback(async () => {
    const version = ++readVersion.current;
    try {
      const { data } = await getManagerDaily(date || undefined);
      if (!current() || version !== readVersion.current) return;
      setDay(data); setReadError(false);
      if (!date) setToday(data.business_date);
    } catch {
      if (current() && version === readVersion.current) setReadError(true);
    }
  }, [date, current]);
  useEffect(() => {
    void refresh();
    return () => { ++readVersion.current; };
  }, [refresh]);
  const transcribing = day?.meetings.some(meeting => meeting.transcript_status === 'transcribing');
  useEffect(() => {
    if (!transcribing) return;
    const timer = window.setInterval(() => { if (!document.hidden) void refresh(); }, 15000);
    return () => window.clearInterval(timer);
  }, [transcribing, refresh]);
  useEffect(() => () => {
    const instance = recording.current;
    recording.current = null;
    if (instance?.active) void instance.stop();
  }, []);
  useEffect(() => {
    if (phase !== 'recording') return;
    const timer = window.setInterval(() => setSeconds(value => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [phase]);

  const start = async () => {
    if (recording.current || saving.current || clip) return;
    const instance = new WavRecorder();
    recording.current = instance;
    setPhase('opening'); setNote(''); setSeconds(0);
    try {
      await instance.start();
      if (!current() || recording.current !== instance) { await instance.stop(); return; }
      setPhase('recording');
    } catch {
      await instance.stop().catch(() => undefined);
      if (current()) {
        recording.current = null; setPhase('idle');
        setNote('无法使用麦克风，请允许麦克风权限后重试。');
      }
    }
  };
  const persist = async (take: Clip) => {
    if (saving.current) return;
    saving.current = true; setPhase('saving'); setNote('');
    try {
      if (take.mediaId === undefined) {
        const uploaded = await uploadMedia(take.file, 'meeting_audio');
        take.mediaId = uploaded.data.id;
      } else {
        const { data } = await getManagerDaily(take.businessDate);
        if (!current()) return;
        if ((data.meetings as Meeting[]).some(item => item.media?.id === take.mediaId)) {
          setClip(null); setNote('录音已保存'); await refresh(); return;
        }
      }
      if (!current()) return;
      await saveManagerMeeting({ media_id: take.mediaId!, duration_seconds: take.duration, title: '晨会' });
      if (current()) { setClip(null); setNote('录音已保存'); await refresh(); }
    } catch {
      if (current()) { setClip(take); setNote('录音保留在本页，请重试保存。'); }
    } finally {
      saving.current = false;
      if (current()) setPhase('idle');
    }
  };
  const stop = async () => {
    const instance = recording.current;
    if (!instance || !day || phase !== 'recording') return;
    recording.current = null; setPhase('saving');
    try {
      const take = await instance.stop();
      if (current()) await persist({ file: new File([take.blob], 'meeting.wav', { type: 'audio/wav' }), duration: take.duration, businessDate: day.business_date });
    } catch {
      if (current()) { setPhase('idle'); setNote('未能保存这段录音，请重新录制。'); }
    }
  };
  const switchDate = (value: string) => {
    const next = value === today ? '' : value;
    if (next !== date) { ++readVersion.current; setDay(null); setReadError(false); setNote(''); setDate(next); }
  };
  const busy = phase !== 'idle' || !!clip;
  const goBack = () => {
    if (location.state?.fromWorkbench) navigate(-1);
    else navigate('/store', { replace: true });
  };
  return <section className="manager-p0-page manager-recordings">
    <header className="manager-p0-head"><div><button type="button" className="manager-p0-back" onClick={goBack}><ArrowLeftOutlined /> 返回</button><h1>晨会录音</h1></div></header>
    <div className="manager-p0-stack">
      {!date && day && <section className="manager-p0-card" aria-label="录制晨会">
        {phase === 'recording' ? <div className="manager-p0-recording"><span className="manager-p0-recording-dot" /><strong>{duration(seconds)}</strong><Button danger icon={<StopOutlined />} onClick={() => void stop()}>结束并保存</Button></div>
          : clip ? <Button type="primary" loading={phase === 'saving'} onClick={() => void persist(clip)}>重试保存</Button>
          : <Button type="primary" size="large" icon={<AudioOutlined />} loading={phase !== 'idle'} onClick={() => void start()}>{phase === 'opening' ? '正在打开麦克风' : phase === 'saving' ? '正在保存录音' : '开始录音'}</Button>}
        {note && <p role="status">{note}</p>}
      </section>}
      <section className="manager-p0-card" aria-label="录音记录">
        <div className="manager-p0-card-head"><h2>录音记录</h2>{today && <input aria-label="录音日期" type="date" max={today} disabled={busy} value={date || today} onChange={e => switchDate(e.target.value)} />}</div>
        {date && <Button size="small" onClick={() => switchDate('')}>回到今天</Button>}
        {readError && <p role="alert">无法读取录音。<Button size="small" onClick={() => void refresh()}>重新加载</Button></p>}
        {!day && !readError && <Spin aria-label="正在读取录音" />}
        {day && (day.meetings.length ? day.meetings.map(meeting => <SavedMeeting key={meeting.id} meeting={meeting} refresh={refresh} />)
          : <p className="manager-p0-muted">{date ? '当天没有录音' : '今天还没有录音'}</p>)}
        {day && day.meetings.length > 0 && <small className="manager-p0-fine">音频和文字稿保留 90 天</small>}
      </section>
    </div>
  </section>;
}

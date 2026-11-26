import { useEffect, useId, useRef, useState } from 'react';
import { Image, message, Modal } from 'antd';
import { CameraOutlined, DownOutlined } from '@ant-design/icons';
import { client, saveManagerAreaPhoto, uploadInspectionCapture, type InspectionArea, type InspectionPhoto } from '../api';
import { mediaPreviewSource } from '../mediaPreview';
import { requestErrorMessage } from '../requestError';
import InspectionPhotoReview from './InspectionPhotoReview';
import { attachCameraPreview } from './cameraPreview';

function PhotoPreview({ photo, label }: { photo: InspectionPhoto; label: string }) {
  const url = photo.media?.url;
  const [src, setSrc] = useState<string>();
  useEffect(() => {
    const source = mediaPreviewSource(url);
    setSrc(undefined);
    if (!source?.authenticated) { setSrc(source?.url); return; }
    let active = true;
    let objectUrl: string | undefined;
    client.get(source.url, { responseType: 'blob' }).then(({ data }) => {
      if (active) { objectUrl = URL.createObjectURL(data); setSrc(objectUrl); }
    }).catch(() => undefined);
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [url]);
  return src ? <Image src={src} alt={label} width={64} height={64} preview={{ mask: false }} />
    : <span className="inspection-photo-unavailable">暂无预览</span>;
}

function InspectionCamera({ label, emptyRoom, onSave, onClose }: {
  label: string; emptyRoom: boolean; onSave: (frame: Blob) => Promise<void>; onClose: () => void;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const taking = useRef(false);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const close = useRef(onClose);
  close.current = onClose;

  useEffect(() => {
    let disposed = false;
    let stream: MediaStream | undefined;
    const stop = () => { stream?.getTracks().forEach(track => track.stop()); };
    const hidden = () => {
      if (document.hidden) { disposed = true; stop(); close.current(); }
    };
    const open = async () => {
      setReady(false); setError('');
      try {
        if (!navigator.mediaDevices?.getUserMedia) throw new Error('camera-unavailable');
        stream = await navigator.mediaDevices.getUserMedia({ audio: false,
          video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1440 } } });
        if (disposed || !video.current) { stop(); return; }
        await attachCameraPreview(video.current, stream);
        if (!disposed) setReady(true);
      } catch (cause) {
        stop();
        if (!disposed) setError(cause instanceof DOMException && cause.name === 'NotAllowedError'
          ? '请在手机设置中允许访问相机，再点重试。'
          : '相机暂时无法使用，请检查相机或在支持摄像头的手机浏览器打开。');
      }
    };
    void open();
    document.addEventListener('visibilitychange', hidden);
    return () => { disposed = true; stop(); document.removeEventListener('visibilitychange', hidden); };
  }, [attempt]);

  const shoot = async () => {
    const element = video.current;
    if (taking.current || !ready || !element?.videoWidth || !element.videoHeight) return;
    taking.current = true; setBusy(true);
    try {
      const canvas = document.createElement('canvas');
      const scale = Math.min(1, 1920 / Math.max(element.videoWidth, element.videoHeight));
      canvas.width = Math.max(1, Math.round(element.videoWidth * scale));
      canvas.height = Math.max(1, Math.round(element.videoHeight * scale));
      const ctx = canvas.getContext('2d');
      if (!ctx) throw new Error('capture-failed');
      ctx.drawImage(element, 0, 0, canvas.width, canvas.height);
      const frame = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.87));
      if (!frame || document.hidden || !video.current) throw new Error('capture-failed');
      await onSave(frame);
    } catch {
      setError('未能取得照片，请重新打开相机拍摄。');
      setReady(false);
    } finally { taking.current = false; setBusy(false); }
  };

  return <Modal open title={label + ' · 现场拍照'} footer={null} closable={!busy}
    maskClosable={false} keyboard={!busy} onCancel={() => { if (!taking.current) onClose(); }}>
    <video ref={video} muted autoPlay playsInline aria-label="相机实时画面"
      style={{ width: '100%', maxHeight: '55dvh', backgroundColor: '#17251e', objectFit: 'contain' }} />
    {error ? <p role="alert">{error}</p> : !ready && <p role="status">正在打开相机…</p>}
    <p className="inspection-camera-note">{emptyRoom ? '确认无人使用后再拍摄。' : ''}请避开人脸、付款码和单据。</p>
    <div className="inspection-actions">{error
      ? <button type="button" onClick={() => setAttempt(n => n + 1)}>重试相机</button>
      : <button type="button" disabled={!ready || busy} onClick={() => void shoot()}>
        {busy ? '保存中…' : '拍摄并保存'}</button>}</div>
  </Modal>;
}

type Props = {
  areas: InspectionArea[]; reviewEnabled: boolean; limit?: number; businessDate: string; submitted: boolean; disabled: boolean;
  historical?: boolean; onBusy?: (value: boolean) => void; onRefresh: () => Promise<void>;
};

export default function ManagerAreaPhotos({ areas, reviewEnabled, limit, businessDate, submitted, disabled, historical = false, onBusy, onRefresh }: Props) {
  const [target, setTarget] = useState<{ area: InspectionArea; photo?: InspectionPhoto }>();
  const [busyArea, setBusyArea] = useState('');
  const [filter, setFilter] = useState<'all' | 'missing' | 'done'>('all');
  const [expanded, setExpanded] = useState<string | null>(historical && areas.length === 1 ? areas[0].key : null);
  const panelId = useId();
  const saving = useRef(false);
  const writable = !historical && limit === 3;
  const pick = (area: InspectionArea, photo?: InspectionPhoto) => {
    if (!writable || disabled || target || saving.current) return;
    if ((submitted || photo) && !window.confirm(
      (photo ? '更换' + area.label + '第 ' + photo.slot + ' 张照片？' : '追加' + area.label + '照片？')
      + (submitted ? '保存后需要重新提交今日巡检。' : '')
    )) return;
    setTarget({ area, photo });
  };

  const save = async (frame: Blob) => {
    if (!target || !writable || saving.current) return;
    const { area, photo } = target;
    saving.current = true;
    setBusyArea(area.key);
    onBusy?.(true);
    try {
      const { data } = await uploadInspectionCapture(frame, area.key, businessDate);
      const base = { area: area.key, business_date: businessDate, ...data };
      await saveManagerAreaPhoto(photo
        ? { ...base, mode: 'replace', photo_id: photo.id, expected_media_id: photo.media_id }
        : { ...base, mode: 'append' });
      message.success(area.label + '照片已保存');
    } catch (error) {
      message.error(requestErrorMessage(error));
    } finally {
      setTarget(undefined);
      try { await onRefresh(); }
      finally { saving.current = false; onBusy?.(false); setBusyArea(''); }
    }
  };

  const done = areas.filter(area => area.done).length;
  const visible = areas.filter(area => filter === 'all' || (filter === 'done' ? area.done : !area.done));
  const standard = visible.filter(area => area.group !== 'spa_rooms');
  const spaRooms = areas.filter(area => area.group === 'spa_rooms');
  const visibleRooms = visible.filter(area => area.group === 'spa_rooms');
  const locked = disabled || !!busyArea;
  const photosFor = (area: InspectionArea) => area.photos ?? (area.photo ? [area.photo] : []);

  function renderPoint(area: InspectionArea) {
    const photos = photosFor(area);
    const open = expanded === area.key;
    const flags = photos.map(p => p.review?.manual_verdict ?? p.review?.result?.verdict);
    const issue = flags.includes('fix') ? '需整改' : flags.includes('retake') ? '需补拍' : '';
    const cameraName = '现场拍照 · ' + area.label;
    return <div key={area.key} className={'manager-p0-area inspection-point' + (open ? ' is-open' : '')} aria-label={area.label}>
      {photos.length > 0 ? <>
        <button type="button" className="inspection-point-summary" aria-label={area.label + '照片与审核'}
          aria-expanded={open} aria-controls={open ? panelId : undefined}
          onClick={() => setExpanded(open ? null : area.key)}>
          <strong>{area.label}</strong><span className="inspection-point-meta"><span>{photos.length} 张</span>
            {issue && <em>{issue}</em>}<DownOutlined aria-hidden /></span>
        </button>
        {writable && photos.length < (limit ?? 0) && <button type="button" className="inspection-add-frame"
          disabled={locked} aria-label={cameraName} onClick={() => pick(area)}><CameraOutlined /></button>}
      </> : <button type="button" className="inspection-point-empty" disabled={locked || !writable}
        aria-label={cameraName} onClick={() => pick(area)}>
        <span><strong>{area.label}</strong><small>{busyArea === area.key ? '保存中…' : '待拍'}</small></span>
        <CameraOutlined aria-hidden />
      </button>}
    </div>;
  }

  function renderAlbum(area: InspectionArea) {
    return <section id={panelId} aria-label={area.label + '已拍照片'} className="inspection-album">
      <div className="inspection-album-head"><h5>{area.label} · 已拍照片</h5>
        <button type="button" aria-label={'收起' + area.label + '照片'} onClick={() => setExpanded(null)}>收起</button></div>
      <div className="inspection-photos">{photosFor(area).map((p, i) => <div className="inspection-photo-row" key={p.id}>
        <div className="inspection-thumb"><PhotoPreview key={p.media_id} photo={p} label={area.label + '照片 ' + (p.slot || i + 1)} />
          {writable && <button type="button" disabled={locked} aria-label={'更换' + area.label + '第 ' + p.slot + ' 张'} onClick={() => pick(area, p)}>更换</button>}</div>
        <InspectionPhotoReview key={p.media_id} photo={p} enabled={reviewEnabled} disabled={locked} onRefresh={onRefresh} />
      </div>)}</div>
    </section>;
  }

  function renderRows(points: InspectionArea[]) {
    const rows = [];
    for (let i = 0; i < points.length; i += 2) {
      const pair = points.slice(i, i + 2);
      const selected = pair.find(area => expanded === area.key);
      rows.push(<div className="inspection-point-pair" key={pair[0].key}>
        {pair.map(renderPoint)}{selected && renderAlbum(selected)}
      </div>);
    }
    return <div className="manager-p0-area-grid inspection-point-grid">{rows}</div>;
  }

  return <section className="inspection-checklist" aria-label={historical ? '历史巡检照片' : '拍摄清单'}>
    <div className="inspection-section-head"><h3>{historical ? businessDate + ' 巡检照片' : '拍摄清单'}</h3>
      {!historical && <span>{writable ? '每处 1～3 张' : '请刷新后上传'}</span>}</div>
    {!historical && <div className="inspection-filters" role="group" aria-label="筛选拍摄点">
      {([['all', '全部', areas.length], ['missing', '待拍', areas.length - done], ['done', '已拍', done]] as const).map(([key, label, count]) =>
        <button type="button" key={key} aria-pressed={filter === key} onClick={() => { setFilter(key); setExpanded(null); }}>
          {label}<span>{count}</span></button>)}
    </div>}
    {target && writable && <InspectionCamera key={target.area.key + businessDate}
      label={(target.area.group === 'spa_rooms' ? 'SPA 房·' : '') + target.area.label}
      emptyRoom={target.area.group === 'spa_rooms' || target.area.key === 'shower_room'}
      onSave={save} onClose={() => { if (!saving.current) setTarget(undefined); }} />}
    {standard.length > 0 && <div>{spaRooms.length > 0 && <h4 className="inspection-category">公共区域</h4>}{renderRows(standard)}</div>}
    {visibleRooms.length > 0 && <section className="inspection-spa-rooms" aria-label="SPA 房">
      <div className="inspection-section-head"><h4 className="inspection-category">SPA 房</h4>
        {!historical && <span aria-live="polite">已拍 {spaRooms.filter(area => area.done).length}/{spaRooms.length} 间</span>}</div>
      {renderRows(visibleRooms)}
    </section>}
    {!visible.length && <p role="status" className="inspection-filter-empty">{filter === 'missing' ? '所有拍摄点都已拍齐。' : '还没有已拍照片。'}</p>}
  </section>;
}

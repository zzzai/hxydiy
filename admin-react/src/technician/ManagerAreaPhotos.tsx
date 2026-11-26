import { useEffect, useRef, useState } from 'react';
import { Image, message, Modal } from 'antd';
import { CameraOutlined } from '@ant-design/icons';
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
  return src ? <Image src={src} alt={label} width={64} height={64} />
    : <span className="inspection-photo-unavailable">暂无预览</span>;
}

function InspectionCamera({ label, onSave, onClose }: {
  label: string; onSave: (frame: Blob) => Promise<void>; onClose: () => void;
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

  const spaRooms = areas.filter(area => area.group === 'spa_rooms');
  const renderArea = (area: InspectionArea) => {
    const photos = area.photos ?? (area.photo ? [area.photo] : []);
    const locked = disabled || !!busyArea || (!writable && !historical);
    return <div key={area.key} className="manager-p0-area" aria-label={area.label}>
      <div className="inspection-area-header"><strong>{area.label}</strong><small aria-live="polite">
        {busyArea === area.key ? '保存中…' : photos.length + ' 张'}
      </small></div>
      {!historical && area.key === 'shower_room' && <p className="inspection-camera-note">确认无人使用后再拍摄。</p>}
      {!!photos.length && <div className="inspection-photos">{photos.map((p, i) => <div className="inspection-photo-row" key={p.id}>
        <div className="inspection-thumb"><PhotoPreview key={p.media_id} photo={p} label={area.label + '照片 ' + (p.slot || i + 1)} />
        {writable && <button type="button" disabled={locked} aria-label={'更换' + area.label + '第 ' + p.slot + ' 张'} onClick={() => pick(area, p)}>更换</button>}</div>
        <InspectionPhotoReview key={p.media_id} photo={p} enabled={reviewEnabled} disabled={locked} onRefresh={onRefresh} />
      </div>)}</div>}
      {writable && photos.length < limit && <div className="inspection-actions">
        <button type="button" disabled={locked} onClick={() => pick(area)}><CameraOutlined /> 现场拍照</button>
      </div>}
    </div>;
  };

  return <section className="manager-p0-card">
    <div className="manager-p0-card-head"><h3>{historical ? businessDate + ' 巡检照片' : '区域照片'}</h3>{!historical && <small>{writable ? '每区 1～3 张' : '请刷新后上传'}</small>}</div>
    {reviewEnabled && !historical && <p className="inspection-camera-note">照片会自动审核。拍摄时请避开人脸、付款码和单据。</p>}
    {target && writable && <InspectionCamera key={target.area.key + businessDate} label={(target.area.group === 'spa_rooms' ? 'SPA 房·' : '') + target.area.label}
      onSave={save} onClose={() => { if (!saving.current) setTarget(undefined); }} />}
    <div className="manager-p0-area-grid">{areas.filter(area => area.group !== 'spa_rooms').map(renderArea)}</div>
    {spaRooms.length > 0 && <section className="inspection-spa-rooms" aria-label="SPA 房">
      <div className="inspection-area-header"><h4>SPA 房</h4>
        {!historical && <small aria-live="polite">已拍 {spaRooms.filter(area => area.done).length}/{spaRooms.length} 间</small>}
      </div>
      {!historical && <p className="inspection-camera-note">每间 1～3 张，请在空房时拍摄。</p>}
      <div className="manager-p0-area-grid">{spaRooms.map(renderArea)}</div>
    </section>}
  </section>;
}

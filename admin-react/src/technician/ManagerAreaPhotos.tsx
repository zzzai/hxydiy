import { useEffect, useRef, useState } from 'react';
import { Image, message } from 'antd';
import { CameraOutlined, PictureOutlined } from '@ant-design/icons';
import { client, saveManagerAreaPhoto, uploadMedia, type InspectionArea, type InspectionPhoto } from '../api';
import { mediaPreviewSource } from '../mediaPreview';
import { requestErrorMessage } from '../requestError';
import InspectionPhotoReview from './InspectionPhotoReview';

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

type Props = {
  areas: InspectionArea[]; reviewEnabled: boolean; limit?: number; businessDate: string; submitted: boolean; disabled: boolean;
  historical?: boolean; onBusy?: (value: boolean) => void; onRefresh: () => Promise<void>;
};

export default function ManagerAreaPhotos({ areas, reviewEnabled, limit, businessDate, submitted, disabled, historical = false, onBusy, onRefresh }: Props) {
  const picker = useRef<HTMLInputElement>(null);
  const target = useRef<{ area: InspectionArea; photo?: InspectionPhoto }>();
  const saving = useRef(false);
  const [busyArea, setBusyArea] = useState('');
  const writable = !historical && limit === 3;
  const pick = (area: InspectionArea, camera: boolean, photo?: InspectionPhoto) => {
    const input = picker.current;
    if (!input || !writable || disabled || saving.current) return;
    if ((submitted || photo) && !window.confirm(
      (photo ? '更换' + area.label + '第 ' + photo.slot + ' 张照片？' : '追加' + area.label + '照片？')
      + (submitted ? '保存后需要重新提交今日巡检。' : '')
    )) return;
    target.current = { area, photo };
    input.value = '';
    input.multiple = !photo && !camera;
    if (camera) input.setAttribute('capture', 'environment');
    else input.removeAttribute('capture');
    input.click();
  };

  const save = async (files: File[]) => {
    const selection = target.current;
    if (!selection || !files.length || !writable || saving.current) return;
    const { area, photo } = selection;
    const remaining = photo ? 1 : limit - (area.photos?.length || 0);
    if (files.length > remaining) { message.warning('本次最多可选 ' + remaining + ' 张照片'); return; }
    saving.current = true;
    onBusy?.(true); setBusyArea(area.key);
    let saved = 0;
    try {
      for (const file of files) {
        const media = await uploadMedia(file, 'daily_area');
        const base = { area: area.key, business_date: businessDate, media_id: media.data.id };
        await saveManagerAreaPhoto(photo
          ? { ...base, mode: 'replace', photo_id: photo.id, expected_media_id: photo.media_id }
          : { ...base, mode: 'append' });
        saved++;
      }
      message.success(area.label + '已保存 ' + saved + ' 张照片');
    } catch (error) {
      message.error((saved ? '已保存 ' + saved + ' 张。' : '') + requestErrorMessage(error));
    } finally {
      try { await onRefresh(); }
      finally { saving.current = false; onBusy?.(false); setBusyArea(''); }
    }
  };

  return <section className="manager-p0-card">
    <div className="manager-p0-card-head"><h3>{historical ? businessDate + ' 巡检照片' : '区域照片'}</h3>{!historical && <small>{writable ? '每区 1～3 张' : '请刷新后上传'}</small>}</div>
    {reviewEnabled && !historical && <p className="inspection-camera-note">新照片由 DeepSeek 自动初审。拍摄时请避开人脸、付款码和单据。</p>}
    <input ref={picker} type="file" accept="image/*" hidden onChange={(event) => void save(Array.from(event.target.files || []))} />
    <div className="manager-p0-area-grid">{areas.map((area) => {
      const photos = area.photos ?? (area.photo ? [area.photo] : []);
      const locked = disabled || !!busyArea || (!writable && !historical);
      return <div key={area.key} className="manager-p0-area" aria-label={area.label}>
        <div className="inspection-area-header"><strong>{area.label}</strong><small aria-live="polite">
          {busyArea === area.key ? '保存中…' : photos.length + ' 张'}
        </small></div>
        {!!photos.length && <div className="inspection-photos">{photos.map((p, i) => <div className="inspection-photo-row" key={p.id}>
          <div className="inspection-thumb"><PhotoPreview key={p.media_id} photo={p} label={area.label + '照片 ' + (p.slot || i + 1)} />
          {writable && <button type="button" disabled={locked} aria-label={'更换' + area.label + '第 ' + p.slot + ' 张'} onClick={() => pick(area, false, p)}>更换</button>}</div>
          <InspectionPhotoReview key={p.media_id} photo={p} enabled={reviewEnabled} disabled={locked} onRefresh={onRefresh} />
        </div>)}</div>}
        {writable && photos.length < limit && <div className="inspection-actions">
          <button type="button" disabled={locked} onClick={() => pick(area, true)}><CameraOutlined /> 拍照</button>
          <button type="button" disabled={locked} onClick={() => pick(area, false)}><PictureOutlined /> 从相册选</button>
        </div>}
      </div>;
    })}</div>
  </section>;
}

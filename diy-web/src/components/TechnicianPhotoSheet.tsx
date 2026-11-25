import { ChevronLeft, ChevronRight, Expand, X } from 'lucide-react';
import { useId, useLayoutEffect, useRef, type MouseEvent, type ReactNode } from 'react';
import type { PublicTechnician } from '../api';

export type CardPhoto = { url: string; kind: 'portrait' | 'work' | 'illustration' };
export const illustrationCaption = 'AI 示意 · 非本人';

type Props = {
  person?: PublicTechnician;
  venue: string;
  lead?: CardPhoto;
  photoIndex?: number;
  failedImages: string[];
  onImageError: (url: string) => void;
  showPhoto: (index: number) => void;
  back: () => void;
  children: ReactNode;
  footer: ReactNode;
};

export default function TechnicianPhotoSheet({ person, venue, lead, photoIndex, failedImages,
  onImageError, showPhoto, back, children, footer }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const body = useRef<HTMLDivElement>(null);
  const opener = useRef<{ button: HTMLButtonElement; top: number }>();
  const startX = useRef<number>();
  const pull = useRef<{ id: number; y: number }>();
  const backdropPress = useRef(false);
  const titleId = useId();
  const zoomed = photoIndex !== undefined;
  const photos = person ? [
    ...(person.portrait_url ? [{ url: person.portrait_url, caption: '工作肖像' }] : []),
    ...person.photos.filter(p => p.url !== person.portrait_url),
  ] : [];
  if (lead?.kind === 'illustration') photos.push({ url: lead.url, caption: illustrationCaption });
  const visible = photos.map((p, index) => ({ ...p, index })).filter(p => !failedImages.includes(p.url));
  const photo = photoIndex === undefined ? undefined : photos[photoIndex];

  useLayoutEffect(() => {
    const el = dialog.current;
    el?.showModal();
    return () => el?.close();
  }, []);
  useLayoutEffect(() => {
    if (!zoomed && body.current && opener.current?.button.isConnected) {
      body.current.scrollTop = opener.current.top;
      opener.current.button.focus({ preventScroll: true });
      opener.current = undefined;
    } else {
      heading.current?.focus({ preventScroll: true });
    }
  }, [person?.key, zoomed]);

  function step(direction: number) {
    if (visible.length < 2) return;
    const current = visible.findIndex(p => p.index === photoIndex);
    showPhoto(visible[(current + direction + visible.length) % visible.length].index);
  }
  function outside(event: MouseEvent<HTMLDialogElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    return event.target === event.currentTarget && (event.clientX < rect.left || event.clientX > rect.right
      || event.clientY < rect.top || event.clientY > rect.bottom);
  }
  function endPull() {
    pull.current = undefined;
    dialog.current?.style.removeProperty('translate');
  }
  const cancel = <button type="button" className="technician-sheet-close"
    aria-label={zoomed ? '返回技师资料' : '返回本店技师'} onClick={back}><X size={20} aria-hidden="true" /></button>;

  return <dialog ref={dialog} className={'technician-sheet' + (zoomed ? ' is-viewer' : '')}
    aria-labelledby={titleId}
    onCancel={e => { e.preventDefault(); e.stopPropagation(); back(); }}
    onKeyDown={e => {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); back(); }
      if (zoomed && (e.key === 'ArrowRight' || e.key === 'ArrowLeft')) {
        e.preventDefault(); e.stopPropagation(); step(e.key === 'ArrowRight' ? 1 : -1);
      }
    }}
    onPointerDown={e => { backdropPress.current = outside(e); }}
    onClick={e => { if (backdropPress.current && outside(e)) back(); backdropPress.current = false; }}
    onPointerCancel={() => { backdropPress.current = false; }}
    onTouchStart={e => e.stopPropagation()} onTouchEnd={e => e.stopPropagation()}>
    {!zoomed && <div className="technician-sheet-handle" aria-hidden="true"
      onPointerDown={e => {
        if (e.button !== 0) return;
        pull.current = { id: e.pointerId, y: e.clientY };
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={e => {
        if (pull.current?.id !== e.pointerId || !dialog.current) return;
        const travel = Math.max(0, e.clientY - pull.current.y);
        dialog.current.style.translate = '0 ' + Math.min(94, travel * .46) + 'px';
      }}
      onPointerUp={e => {
        if (pull.current?.id !== e.pointerId) return;
        const close = e.clientY - pull.current.y > 68;
        endPull();
        if (close) back();
      }} onPointerCancel={endPull}><span /></div>}
    <header className="technician-sheet-head">
      <div><h2 id={titleId} ref={heading} tabIndex={-1}>{person?.label || '技师资料'}{zoomed && ' · 工作相册'}</h2>
        {!zoomed && person && <p className="technician-sheet-meta">
          {person.experience && <strong>{/^\d/.test(person.experience) ? '从业 ' : ''}{person.experience}</strong>}
          {venue && <span>{venue}</span>}
        </p>}
      </div>{cancel}
    </header>
    {person ? <>
      <div className="technician-sheet-body technician-detail" ref={body} hidden={zoomed}>
        {visible.length > 0 && <div className={'technician-sheet-photos count-' + Math.min(visible.length, 3)}>
          {visible.slice(0, 3).map((item, i) => <button key={item.url} type="button" className="technician-sheet-photo"
            aria-label={'放大' + person.label + '的' + item.caption}
            onClick={e => {
              opener.current = { button: e.currentTarget, top: body.current?.scrollTop ?? 0 };
              showPhoto(item.index);
            }}>
            <img src={item.url} alt="" onError={() => onImageError(item.url)} />
            {(item.url !== person.portrait_url || i > 0) && <span className="technician-photo-caption">{item.caption}</span>}
            {i === 0 && <Expand size={16} className="technician-sheet-expand" aria-hidden="true" />}
            {i === 2 && visible.length > 3 && <span className="technician-photo-count">+{visible.length - 3}</span>}
          </button>)}
        </div>}
        {children}
      </div>
      {!zoomed && footer}
      {zoomed && <div className="technician-viewer"
        onTouchStart={e => { startX.current = e.touches[0]?.clientX; }}
        onTouchEnd={e => {
          const delta = e.changedTouches[0].clientX - (startX.current ?? e.changedTouches[0].clientX);
          startX.current = undefined;
          if (Math.abs(delta) > 45) step(delta < 0 ? 1 : -1);
        }}>
        {photo && !failedImages.includes(photo.url)
          ? <img src={photo.url} alt={photo.caption} onError={() => onImageError(photo.url)} />
          : <p className="technician-unavailable-photo" role="status">这张照片暂时打不开</p>}
        <div>
          {visible.length > 1 && <button type="button" aria-label="上一张" onClick={() => step(-1)}><ChevronLeft /></button>}
          <p aria-live="polite">{photo?.caption}{visible.length > 1 && visible.some(p => p.index === photoIndex)
            && <small>{visible.findIndex(p => p.index === photoIndex) + 1} / {visible.length}</small>}</p>
          {visible.length > 1 && <button type="button" aria-label="下一张" onClick={() => step(1)}><ChevronRight /></button>}
        </div>
      </div>}
    </> : <div className="technician-message"><p>这位技师的资料已下架</p><button type="button" onClick={back}>返回技师列表</button></div>}
  </dialog>;
}

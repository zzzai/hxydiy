import { ArrowLeft, Check, ChevronLeft, ChevronRight, Expand, Images, MapPin, X } from 'lucide-react';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { getStoreTechnicians, selectableTechnicians, type PublicTechnician, type SelectableTechnician } from '../api';
import { assetPath, displayProjectName, formatMoney, type Project } from '../domain';
import type { TechnicianView } from '../technicianNavigation';
import './technician-showcase.css';

type Props = {
  view: TechnicianView;
  storeName: string;
  projects: Project[];
  canEdit: boolean;
  directoryFooter?: ReactNode;
  navigate: (view: TechnicianView, replace?: boolean) => void;
  back: () => void;
  finish: () => void;
  onProject: (project: Project) => void;
  onRequest: (technician: SelectableTechnician) => void;
};

function Tenure({ value }: { value: string }) {
  return /^\d/.test(value)
    ? <><span className="technician-tenure-label">从业</span>{' '}<strong>{value}</strong></>
    : <strong>{value}</strong>;
}

function TechnicianName({ label }: { label: string }) {
  const number = /^(\d+)\s*号技师$/.exec(label);
  if (!number) return <>{label}</>;
  return <><span className="technician-code">{number[1]}</span>{' '}<span className="technician-code-suffix">号技师</span></>;
}

type CardPhoto = { url: string; atWork: boolean };

function DirectoryCard({ person, photo, projectName, requestLabel, canRequest, onOpen, onPhotoError }: {
  person: PublicTechnician;
  photo?: CardPhoto;
  projectName?: string;
  requestLabel: string;
  canRequest: boolean;
  onOpen: () => void;
  onPhotoError: (url: string) => void;
}) {
  return <li>
    <button type="button" className="technician-card" data-profile={person.key} onClick={onOpen}>
      {photo && <span className="technician-card-media">
        <img className="technician-card-photo" src={photo.url} alt="" loading="lazy" onError={() => onPhotoError(photo.url)} />
        {photo.atWork && <span className="technician-photo-caption">服务现场</span>}
      </span>}
      <span className="technician-card-body">
        <strong className="technician-card-name"><TechnicianName label={person.label} /></strong>
        <ChevronRight className="technician-card-arrow" size={15} aria-hidden="true" />
        {(person.experience || person.tags.length > 0) && <span className="technician-card-meta">
          {person.experience && <span className="technician-card-experience"><Tenure value={person.experience} /></span>}
          {person.tags[0] && <span>{person.tags[0]}</span>}
        </span>}
        {projectName && <span className="technician-card-service">可做{projectName}</span>}
        {requestLabel && <span className={'technician-card-request' + (canRequest ? ' open' : '')}>{requestLabel}</span>}
      </span>
    </button>
  </li>;
}

export default function TechnicianShowcase({ view, storeName, projects, canEdit, navigate, back, finish, onProject, onRequest, directoryFooter }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const detailScroll = useRef<HTMLDivElement>(null);
  const listScroll = useRef<HTMLDivElement>(null);
  const lastProfile = useRef<string>();
  const swipeX = useRef<number>();
  const check = useRef<AbortController>();
  const [profiles, setProfiles] = useState<PublicTechnician[]>([]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [attempt, setAttempt] = useState(0);
  const [failedImages, setFailedImages] = useState<string[]>([]);
  const [checking, setChecking] = useState(false);
  const [notice, setNotice] = useState('');
  const person = profiles.find(p => p.key === view.profile);
  const project = projects.find(p => p.id === view.projectId);
  const inProject = view.projectId !== undefined;
  const available = (p: PublicTechnician) => Boolean(project && p.technician_id && p.requestable_project_ids.includes(project.id));
  const peers = project ? [...profiles].sort((a, b) => Number(available(b)) - Number(available(a))) : profiles;
  const requestCount = profiles.filter(p => inProject ? available(p) : p.requestable_project_ids.length > 0).length;
  const next = person && peers.length > 1 ? peers[(peers.findIndex(p => p.key === person.key) + 1) % peers.length] : null;
  const services = person ? projects.filter(p => person.project_ids.includes(p.id)) : [];
  const hasPortrait = (p: PublicTechnician) => Boolean(p.portrait_url && !failedImages.includes(p.portrait_url));
  const portraitVisible = Boolean(person && hasPortrait(person));
  const markFailed = (url: string) => setFailedImages(urls => urls.includes(url) ? urls : [...urls, url]);
  const photos = person ? [...(person.portrait_url ? [{url: person.portrait_url, caption: person.label + ' · 工作肖像'}] : []), ...person.photos] : [];
  const photo = view.photo === undefined ? undefined : photos[view.photo];

  useEffect(() => {
    const el = dialog.current;
    el?.showModal();
    return () => el?.close();
  }, []);
  useEffect(() => {
    const request = new AbortController();
    setStatus('loading');
    setProfiles([]);
    getStoreTechnicians(view.storeId, request.signal).then(items => {
      if (!request.signal.aborted) { setProfiles(items); setStatus('ready'); }
    }).catch(() => { if (!request.signal.aborted) setStatus('error'); });
    return () => request.abort();
  }, [view.storeId, attempt]);
  useEffect(() => {
    setChecking(false);
    setNotice('');
    if (view.profile && view.profile !== lastProfile.current) detailScroll.current?.scrollTo(0, 0);
    if (!view.profile && lastProfile.current) {
      const previous = Array.from(listScroll.current?.querySelectorAll<HTMLButtonElement>('button[data-profile]') || [])
        .find(item => item.dataset.profile === lastProfile.current);
      previous?.focus({preventScroll: true});
    }
    lastProfile.current = view.profile;
    return () => check.current?.abort();
  }, [view.profile, view.projectId]);

  const requestPerson = async () => {
    if (!person?.technician_id || !project || !canEdit || checking) return;
    const controller = new AbortController();
    check.current?.abort();
    check.current = controller;
    setChecking(true);
    setNotice('');
    try {
      const items = await selectableTechnicians(view.storeId, project.id, controller.signal);
      if (controller.signal.aborted) return;
      const match = items.find(item => item.id === person.technician_id);
      if (match) { onRequest(match); return; }
      setProfiles(rows => rows.map(row => row.key === person.key
        ? { ...row, requestable_project_ids: row.requestable_project_ids.filter(id => id !== project.id) } : row));
      setNotice('这位技师现在无法点名。');
    } catch {
      if (!controller.signal.aborted) setNotice('暂时无法确认能否点名，请再试一次。');
    } finally {
      if (!controller.signal.aborted) setChecking(false);
    }
  };
  const openPhoto = (index: number) => navigate({...view, photo: index}, view.photo !== undefined);
  const stepPhoto = (step: number) => {
    const index = (view.photo ?? 0) + step;
    if (index >= 0 && index < photos.length) openPhoto(index);
  };
  const endSwipe = (event: React.TouchEvent) => {
    event.stopPropagation();
    const start = swipeX.current;
    swipeX.current = undefined;
    if (start === undefined) return;
    const distance = event.changedTouches[0].clientX - start;
    if (Math.abs(distance) > 45) stepPhoto(distance < 0 ? 1 : -1);
  };

  const seeService = (p: Project) => inProject ? finish() : onProject(p);
  const statusText = person && (inProject
    ? (available(person) ? '点名由店长确认'
      : profiles.some(available) ? '这位技师目前不能点名此项目。' : '这个项目今天由门店安排技师。')
    : person.requestable_project_ids.length ? '点名由店长确认' : '今天由门店安排技师。');

  const directoryGroups = inProject && requestCount > 0 && requestCount < peers.length
    ? [{ title: '本项目可点名', rows: peers.filter(available) }, { title: '其他技师', rows: peers.filter(p => !available(p)) }]
    : [{ title: '', rows: peers }];
  const cardPhoto = (p: PublicTechnician): CardPhoto | undefined => {
    if (hasPortrait(p)) return { url: p.portrait_url, atWork: false };
    const scene = p.photos.find(item => !failedImages.includes(item.url));
    if (scene) return { url: scene.url, atWork: true };
  };
  const useCover = status === 'ready' && peers.length > 0 && !peers.some(cardPhoto);
  const renderCard = (p: PublicTechnician) => {
    const canRequest = inProject ? available(p) : p.requestable_project_ids.length > 0;
    const requestLabel = canRequest ? (inProject ? '可点名' : '可按项目点名') : '门店安排';
    const firstService = !inProject && projects.find(item => p.project_ids.includes(item.id));
    return <DirectoryCard key={p.key} person={p} photo={cardPhoto(p)} canRequest={canRequest}
      projectName={firstService ? displayProjectName(firstService) : undefined}
      requestLabel={requestCount ? requestLabel : ''}
      onOpen={() => navigate({...view, profile: p.key, photo: undefined})}
      onPhotoError={markFailed} />;
  };
  const venue = storeName.replace(/^(?:荷小悦\s*[-·]?\s*)?草本泡脚[（(]([^（）()]+)[）)]$/, '$1');
  const compact = person && !portraitVisible && !person.tags.length && !person.introduction && !person.photos.some(item => !failedImages.includes(item.url)) && !services.length;
  return <dialog className={compact ? 'technician-showcase compact' : 'technician-showcase'} ref={dialog} aria-labelledby="technician-title"
    onCancel={event => { event.preventDefault(); back(); }}
    onKeyDown={event => {
      if (event.key !== 'Escape') return;
      // The underlying project also listens for Escape during its exit animation.
      event.preventDefault();
      event.stopPropagation();
      back();
    }}>
    {view.profile ? <header className="mini-detail-nav technician-nav">
      <button type="button" onClick={back} aria-label={photo ? '返回技师主页' : '返回本店技师'}>{photo ? <X /> : <ArrowLeft />}</button>
      <strong id="technician-title">{photo ? '工作相册' : '技师主页'}</strong>
      <span title={storeName}>{venue}</span>
    </header> : <header className={'technician-directory-head' + (useCover ? ' has-cover' : '')}>
      {useCover && <img className="technician-directory-cover" src={assetPath('technician-team-craft-v1.webp')} alt="" />}
      <button type="button" className="technician-directory-back" onClick={back} aria-label="返回上一页"><ChevronLeft size={23} /></button>
      <p className="technician-venue" title={storeName}><MapPin size={14} aria-hidden="true" />{venue}</p>
      <h1 id="technician-title">本店技师</h1>
    </header>}
    {status !== 'ready' ? <div className="technician-message" role="status">{status === 'loading' ? '正在加载技师资料…' :
      <><p>技师资料暂时打不开</p><button type="button" onClick={() => setAttempt(n => n + 1)}>重新加载</button></>}</div> :
      <>
        <div ref={listScroll} className="technician-scroll technician-directory" hidden={Boolean(view.profile)}>
          {peers.length ? <>
            <div className="technician-directory-context">
              <p>{project && <strong>{displayProjectName(project)}</strong>}<span>共 {peers.length} 位技师</span></p>
              {requestCount > 0 && <span>{inProject ? `${requestCount} 位可点名` : '点名由店长确认'}</span>}
            </div>
            <div className="technician-list">{directoryGroups.map(group => {
              const photographed = group.rows.filter(cardPhoto);
              const names = group.rows.filter(p => !cardPhoto(p));
              return <section key={group.title} className="technician-group">
                {group.title && <h2>{group.title}</h2>}
                {photographed.length > 0 && <ul className="technician-gallery" aria-label={group.title || '本店技师照片'}>{photographed.map(renderCard)}</ul>}
                {names.length > 0 && <>
                  {photographed.length > 0 && <h3>更多本店技师</h3>}
                  <ul className="technician-roster" aria-label={group.title || '本店技师名单'}>{names.map(renderCard)}</ul>
                </>}
              </section>;
            })}</div>
            {requestCount === 0 && <div className="technician-arrangement">
              <span>本次由门店安排技师</span>
              <button type="button" onClick={finish}>{inProject ? '返回当前项目' : '去选项目'}<ChevronRight size={15} aria-hidden="true" /></button>
            </div>}
          </> : <div className="technician-message"><p>本店暂未展示技师资料</p><button type="button" onClick={finish}>返回选项目</button></div>}
        </div>
        {view.profile && !person && <div className="technician-message"><p>这位技师的资料已下架</p><button type="button" onClick={back}>返回技师列表</button></div>}
        {person && !photo && <>
          <div ref={detailScroll} className="technician-scroll technician-detail">
            <section className={'technician-identity' + (portraitVisible ? ' has-portrait' : '')}>
              {portraitVisible && <button type="button" className="technician-portrait" onClick={() => openPhoto(0)} aria-label={'放大' + person.label + '的肖像'}>
                <img src={person.portrait_url} alt={person.label + '的工作肖像'} onError={() => markFailed(person.portrait_url)} /><Expand size={16} />
              </button>}
              <div className="technician-person"><h1><TechnicianName label={person.label} /></h1>{person.experience && <p className="technician-experience"><Tenure value={person.experience} /></p>}
                {person.tags.length > 0 && <ul className="technician-tags" aria-label="服务风格">{person.tags.map(tag => <li key={tag}>{tag}</li>)}</ul>}
              </div>
            </section>
            {person.introduction && <p className="technician-intro">{person.introduction}</p>}
            {services.length > 0 && <section className="technician-section"><h2>可做项目</h2><ul className="technician-services">{services.map(p => {
              const price = p.prices.find(v => v.price_type === 'store')?.amount_cents;
              const line = <><span><b>{displayProjectName(p)}</b>{p.duration_min != null && <small>{p.duration_min} 分钟</small>}</span>
                {price != null && <strong>{formatMoney(price)}</strong>}</>;
              return <li key={p.id}>{inProject ? <div>{line}</div> : <button type="button" onClick={() => seeService(p)}>{line}<ChevronRight size={18} /></button>}</li>;
            })}</ul></section>}
            {person.photos.some(item => !failedImages.includes(item.url)) && <section className="technician-section"><h2><Images size={19} />服务现场</h2>
              <div className="technician-photos">{person.photos.map((picture, i) => !failedImages.includes(picture.url) &&
                <button type="button" key={picture.url} onClick={() => openPhoto(i + Number(Boolean(person.portrait_url)))}><img src={picture.url} alt="" loading="lazy" onError={() => markFailed(picture.url)} /><span>{picture.caption}</span></button>)}</div>
            </section>}
          </div>
          <footer className="technician-dock"><p role="status">{notice || statusText}</p>
            <nav aria-label="技师主页操作">{next && <button type="button" className="technician-secondary" onClick={() => navigate({...view, profile: next.key, photo: undefined}, true)}>
              看{next.label}</button>}
              {canEdit && available(person) ? <button type="button" className="technician-primary" onClick={requestPerson} disabled={checking}><Check size={17} />{checking ? '确认中…' : '本份服务点名'}</button>
                : <button type="button" className="technician-primary" onClick={() => inProject ? finish() : services[0] ? seeService(services[0]) : finish()}>
                  {inProject ? '返回当前项目' : services.length ? '看项目详情' : '看本店项目'}<ChevronRight size={17} /></button>}
            </nav></footer>
        </>}
        {person && photo && <div className="technician-viewer" onTouchStart={e => {e.stopPropagation(); swipeX.current=e.touches[0]?.clientX;}}
          onTouchEnd={endSwipe}
          onKeyDown={e => { if(e.key==='ArrowRight')stepPhoto(1); if(e.key==='ArrowLeft')stepPhoto(-1); }}>
          {failedImages.includes(photo.url) ? <p className="technician-unavailable-photo" role="status">这张照片暂时打不开</p>
            : <img src={photo.url} alt={photo.caption} onError={() => markFailed(photo.url)} />}<div><button type="button" aria-label="上一张" disabled={!view.photo} onClick={() => stepPhoto(-1)}><ChevronLeft /></button>
            <p>{photo.caption}<small>{(view.photo ?? 0) + 1} / {photos.length}</small></p>
            <button type="button" aria-label="下一张" disabled={view.photo === photos.length - 1} onClick={() => stepPhoto(1)}><ChevronRight /></button></div>
        </div>}
      </>}
    {directoryFooter && <div className="technician-directory-foot">{directoryFooter}</div>}
  </dialog>;
}

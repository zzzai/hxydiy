import { ArrowLeft, Check, ChevronLeft, ChevronRight, Expand, Images, UserRound, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { getStoreTechnicians, selectableTechnicians, type PublicTechnician, type SelectableTechnician } from '../api';
import { displayProjectName, formatMoney, type Project } from '../domain';
import type { TechnicianView } from '../technicianNavigation';
import './technician-showcase.css';

type Props = {
  view: TechnicianView;
  storeName: string;
  projects: Project[];
  canEdit: boolean;
  navigate: (view: TechnicianView, replace?: boolean) => void;
  back: () => void;
  finish: () => void;
  onProject: (project: Project) => void;
  onRequest: (technician: SelectableTechnician) => void;
};

function Portrait({ person }: { person: PublicTechnician }) {
  const [failed, setFailed] = useState('');
  if (person.portrait_url && person.portrait_url !== failed) {
    return <img alt={person.label + '的工作肖像'} src={person.portrait_url} onError={() => setFailed(person.portrait_url)} />;
  }
  const number = /^(\d+)\s*号/.exec(person.label)?.[1];
  return <span aria-hidden="true" className="technician-monogram">{number || (/^[\u4e00-\u9fff]{2,5}$/.test(person.label) ? person.label.slice(-1) : <UserRound />)}</span>;
}

function experience(person: PublicTechnician) {
  return person.experience && (/^\d/.test(person.experience) ? '从业 ' + person.experience : person.experience);
}

export default function TechnicianShowcase({ view, storeName, projects, canEdit, navigate, back, finish, onProject, onRequest }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const detailScroll = useRef<HTMLDivElement>(null);
  const listScroll = useRef<HTMLDivElement>(null);
  const lastProfile = useRef<string>();
  const swipeX = useRef<number>();
  const check = useRef<AbortController>();
  const [profiles, setProfiles] = useState<PublicTechnician[]>([]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [attempt, setAttempt] = useState(0);
  const [checking, setChecking] = useState(false);
  const [notice, setNotice] = useState('');
  const person = profiles.find(p => p.key === view.profile);
  const project = projects.find(p => p.id === view.projectId);
  const inProject = view.projectId !== undefined;
  const available = (p: PublicTechnician) => Boolean(project && p.technician_id && p.requestable_project_ids.includes(project.id));
  const peers = project ? [...profiles].sort((a, b) => Number(available(b)) - Number(available(a))) : profiles;
  const next = person && peers.length > 1 ? peers[(peers.findIndex(p => p.key === person.key) + 1) % peers.length] : null;
  const services = person ? projects.filter(p => person.project_ids.includes(p.id)) : [];
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
    ? (available(person) ? '点名由店长确认' : '这个项目今天由门店安排技师。')
    : person.requestable_project_ids.length ? '点名由店长确认' : '今天由门店安排技师。');

  const compact = person && !person.portrait_url && !person.tags.length && !person.introduction && !person.photos.length && !services.length;
  return <dialog className={compact ? 'technician-showcase compact' : 'technician-showcase'} ref={dialog} aria-labelledby="technician-title"
    onCancel={event => { event.preventDefault(); back(); }}
    onKeyDown={event => {
      if (event.key !== 'Escape') return;
      // The underlying project also listens for Escape during its exit animation.
      event.preventDefault();
      event.stopPropagation();
      back();
    }}>
    <header className="mini-detail-nav technician-nav">
      <button type="button" onClick={back} aria-label={photo ? '返回技师主页' : view.profile ? '返回本店技师' : '返回上一页'}>{photo ? <X /> : <ArrowLeft />}</button>
      <strong id="technician-title">{photo ? '工作相册' : view.profile ? '技师主页' : '本店技师'}</strong>
      <span>{storeName}</span>
    </header>
    {status !== 'ready' ? <div className="technician-message" role="status">{status === 'loading' ? '正在加载技师资料…' :
      <><p>技师资料暂时打不开</p><button type="button" onClick={() => setAttempt(n => n + 1)}>重新加载</button></>}</div> :
      <>
        <div ref={listScroll} className="technician-scroll" hidden={Boolean(view.profile)}>
          {peers.length ? <ul className="technician-list" aria-label="本店技师名单">{peers.map(p =>
            <li key={p.key}><button data-profile={p.key} type="button" onClick={() => navigate({...view, profile: p.key, photo: undefined})}>
              <span className="technician-tile"><Portrait person={p} /></span>
              <span className="technician-list-copy"><b>{p.label}</b>{p.experience && <span>{experience(p)}</span>}
                {p.tags.length > 0 && <small>{p.tags.slice(0, 2).join(' · ')}</small>}</span>
              {inProject && available(p) && <small className="technician-eligible">可点名</small>}<ChevronRight size={18} aria-hidden="true" />
            </button></li>)}</ul> : <div className="technician-message"><p>本店暂未展示技师资料</p><button type="button" onClick={finish}>返回选项目</button></div>}
        </div>
        {view.profile && !person && <div className="technician-message"><p>这位技师的资料已下架</p><button type="button" onClick={back}>返回技师列表</button></div>}
        {person && !photo && <>
          <div ref={detailScroll} className="technician-scroll technician-detail">
            <section className={'technician-identity' + (person.portrait_url ? ' has-portrait' : '')}>
              {person.portrait_url
                ? <button type="button" className="technician-portrait" onClick={() => openPhoto(0)} aria-label={'放大' + person.label + '的肖像'}><Portrait person={person} /><Expand size={16} /></button>
                : <div className="technician-tile large"><Portrait person={person} /></div>}
              <div className="technician-person"><h1>{person.label}</h1>{person.experience && <p className="technician-experience">{experience(person)}</p>}
                {person.tags.length > 0 && <ul className="technician-tags" aria-label="服务风格">{person.tags.map(tag => <li key={tag}>{tag}</li>)}</ul>}
              </div>
            </section>
            {person.introduction && <p className="technician-intro">{person.introduction}</p>}
            {person.photos.length > 0 && <section className="technician-section"><h2><Images size={19} />服务现场</h2>
              <div className="technician-photos">{person.photos.map((picture, i) =>
                <button type="button" key={picture.url} onClick={() => openPhoto(i + Number(Boolean(person.portrait_url)))}><img src={picture.url} alt="" loading="lazy" /><span>{picture.caption}</span></button>)}</div>
            </section>}
            {services.length > 0 && <section className="technician-section"><h2>可做项目</h2><ul className="technician-services">{services.map(p => {
              const price = p.prices.find(v => v.price_type === 'store')?.amount_cents;
              const line = <><span><b>{displayProjectName(p)}</b>{p.duration_min != null && <small>{p.duration_min} 分钟</small>}</span>
                {price != null && <strong>{formatMoney(price)}</strong>}</>;
              return <li key={p.id}>{inProject ? <div>{line}</div> : <button type="button" onClick={() => seeService(p)}>{line}<ChevronRight size={18} /></button>}</li>;
            })}</ul></section>}
          </div>
          <footer className="technician-dock"><p role="status">{notice || statusText}</p>
            <nav aria-label="技师主页操作">{next && <button type="button" className="technician-secondary" onClick={() => navigate({...view, profile: next.key, photo: undefined}, true)}>
              <span className="technician-mini"><Portrait person={next} /></span>看{next.label}</button>}
              {canEdit && available(person) ? <button type="button" className="technician-primary" onClick={requestPerson} disabled={checking}><Check size={17} />{checking ? '确认中…' : '本份服务点名'}</button>
                : <button type="button" className="technician-primary" onClick={() => inProject ? finish() : services[0] ? seeService(services[0]) : finish()}>
                  {inProject ? '返回当前项目' : services.length ? '看项目详情' : '看本店项目'}<ChevronRight size={17} /></button>}
            </nav></footer>
        </>}
        {person && photo && <div className="technician-viewer" onTouchStart={e => {e.stopPropagation(); swipeX.current=e.touches[0]?.clientX;}}
          onTouchEnd={endSwipe}
          onKeyDown={e => { if(e.key==='ArrowRight')stepPhoto(1); if(e.key==='ArrowLeft')stepPhoto(-1); }}>
          <img src={photo.url} alt={photo.caption} /><div><button type="button" aria-label="上一张" disabled={!view.photo} onClick={() => stepPhoto(-1)}><ChevronLeft /></button>
            <p>{photo.caption}<small>{(view.photo ?? 0) + 1} / {photos.length}</small></p>
            <button type="button" aria-label="下一张" disabled={view.photo === photos.length - 1} onClick={() => stepPhoto(1)}><ChevronRight /></button></div>
        </div>}
      </>}
  </dialog>;
}

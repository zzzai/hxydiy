import { Check, ChevronDown, ChevronLeft, ChevronRight, Clipboard, Clock3, MapPin } from 'lucide-react';
import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { getStoreTechnicians, selectableTechnicians, type PublicTechnician, type SelectableTechnician, type StoreSummary } from '../api';
import { displayProjectName, formatMoney, projectImage, type Project } from '../domain';
import { safeStoreContact, STORE_CONTACTS } from '../returnEntry';
import type { TechnicianView } from '../technicianNavigation';
import TechnicianPhotoSheet from './TechnicianPhotoSheet';
import './technician-showcase.css';

type Props = {
  view: TechnicianView;
  store?: StoreSummary;
  projects: Project[];
  canEdit: boolean;
  directoryFooter?: ReactNode;
  navigate: (view: TechnicianView, replace?: boolean) => void;
  back: () => void;
  finish: () => void;
  onProject: (project: Project, requested?: SelectableTechnician) => void;
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

type CardPhoto = { url: string; kind: 'portrait' | 'work' };

function DirectoryCard({ person, photo, projectName, requestLabel, canRequest, onOpen, onPhotoError }: {
  person: PublicTechnician;
  photo?: CardPhoto;
  projectName?: string;
  requestLabel: string;
  canRequest: boolean;
  onOpen: () => void;
  onPhotoError: (url: string) => void;
}) {
  const bodyId = useId();
  const caption = photo?.kind === 'work' ? '服务现场' : '';
  return <li>
    <button type="button" className="technician-card" data-profile={person.key} aria-haspopup="dialog" onClick={onOpen}
      aria-labelledby={caption ? `${bodyId} ${bodyId}-photo` : bodyId}>
      {photo && <span className="technician-card-media">
        <img className="technician-card-photo" src={photo.url} alt="" loading="lazy" onError={() => onPhotoError(photo.url)} />
        {caption && <span id={bodyId + '-photo'} className="technician-photo-caption">{caption}</span>}
      </span>}
      <span id={bodyId} className="technician-card-body">
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

function StoreVisit({ store }: { store: StoreSummary }) {
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copied' | 'manual'>('idle');
  const address = store.address?.trim();
  const hours = store.business_hours?.trim();
  if (!address && !hours) return null;
  const copyAddress = async () => {
    try {
      if (!address) return;
      await navigator.clipboard.writeText(address);
      setCopyStatus('copied');
    } catch {
      setCopyStatus('manual');
    }
  };
  return <section className="technician-section technician-visit" aria-label="到店信息">
    <details>
      <summary><MapPin size={16} aria-hidden="true" />{address && hours ? '门店地址与营业时间' : address ? '门店地址' : '营业时间'}<ChevronDown size={16} aria-hidden="true" /></summary>
      <dl>
      {hours && <div><dt><Clock3 size={16} aria-hidden="true" />营业时间</dt><dd>{hours}</dd></div>}
      {address && <div><dt><MapPin size={16} aria-hidden="true" />门店地址</dt>
        <dd><span className="technician-address">{address}</span>
          <button type="button" onClick={() => void copyAddress()} aria-label="复制门店地址"><Clipboard size={14} aria-hidden="true" />复制地址</button>
          {copyStatus !== 'idle' && <small role="status">{copyStatus === 'copied' ? '地址已复制' : '请选中上方地址复制'}</small>}
        </dd></div>}
      </dl>
    </details>
  </section>;
}

export default function TechnicianShowcase({ view, store, projects, canEdit, navigate, back, finish, onProject, onRequest, directoryFooter }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const servicesSection = useRef<HTMLElement>(null);
  const listPosition = useRef(view.directoryTop ?? 0);
  const listScroll = useRef<HTMLDivElement>(null);
  const lastProfile = useRef<string>();
  const check = useRef<AbortController>();
  const [profiles, setProfiles] = useState<PublicTechnician[]>([]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [attempt, setAttempt] = useState(0);
  const [styleFilter, setStyleFilter] = useState(view.directoryTag ?? '');
  const [failedImages, setFailedImages] = useState<string[]>([]);
  const [checking, setChecking] = useState(false);
  const [notice, setNotice] = useState('');
  const person = profiles.find(p => p.key === view.profile);
  const project = projects.find(p => p.id === view.projectId);
  const inProject = view.projectId !== undefined;
  const available = (p: PublicTechnician) => Boolean(project && p.technician_id && p.requestable_project_ids.includes(project.id));
  const peers = project ? [...profiles].sort((a, b) => Number(available(b)) - Number(available(a))) : profiles;
  const requestCount = profiles.filter(p => inProject ? available(p) : p.requestable_project_ids.length > 0).length;
  const services = person ? projects.filter(p => person.project_ids.includes(p.id)) : [];
  if (person && !inProject && canEdit) {
    const nameable = (service: Project) => person.requestable_project_ids.includes(service.id);
    services.sort((a, b) => Number(nameable(b)) - Number(nameable(a)));
  }
  const hasPortrait = (p: PublicTechnician) => Boolean(p.portrait_url && !failedImages.includes(p.portrait_url));
  const markFailed = (url: string) => setFailedImages(urls => urls.includes(url) ? urls : [...urls, url]);

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
      if (request.signal.aborted) return;
      setProfiles(items.filter(p => p.portrait_url || p.photos.some(photo => photo.url)));
      setStatus('ready');
    }).catch(() => { if (!request.signal.aborted) setStatus('error'); });
    return () => request.abort();
  }, [view.storeId, attempt]);
  useEffect(() => {
    setChecking(false);
    setNotice('');
    if (view.profile && view.profile !== lastProfile.current) {
      setStyleFilter(view.directoryTag ?? '');
      listPosition.current = view.directoryTop ?? 0;
      if (listScroll.current) listScroll.current.scrollTop = listPosition.current;
    }
    if (!view.profile && lastProfile.current) {
      const previous = Array.from(listScroll.current?.querySelectorAll<HTMLButtonElement>('button[data-profile]') || [])
        .find(item => item.dataset.profile === lastProfile.current);
      if (listScroll.current) listScroll.current.scrollTop = listPosition.current;
      previous?.focus({preventScroll: true});
    }
    lastProfile.current = view.profile;
    return () => check.current?.abort();
  }, [view.profile, view.projectId, view.photo, canEdit]);

  const requestPerson = async (service: Project) => {
    if (!person?.technician_id || !canEdit || checking || !person.requestable_project_ids.includes(service.id)) return;
    const controller = new AbortController();
    check.current?.abort();
    check.current = controller;
    setChecking(true);
    setNotice('');
    try {
      const items = await selectableTechnicians(view.storeId, service.id, controller.signal);
      if (controller.signal.aborted) return;
      const match = items.find(item => item.id === person.technician_id);
      if (match) {
        if (inProject) onRequest(match);
        else onProject(service, match);
        return;
      }
      setProfiles(rows => rows.map(row => row.key === person.key
        ? { ...row, requestable_project_ids: row.requestable_project_ids.filter(id => id !== service.id) } : row));
      setNotice('这位技师现在无法点名。');
    } catch {
      if (!controller.signal.aborted) setNotice('暂时无法确认能否点名，请再试一次。');
    } finally {
      if (!controller.signal.aborted) setChecking(false);
    }
  };
  const openPhoto = (index: number) => navigate({...view, photo: index}, view.photo !== undefined);

  const offersNamedService = person && services.some(service => person.requestable_project_ids.includes(service.id));
  const contactUrl = person && !inProject && !offersNamedService && store?.id === view.storeId
    ? safeStoreContact(STORE_CONTACTS[view.storeId])?.addUrl : undefined;
  const statusText = person && (inProject
    ? (available(person) ? (canEdit ? '点名由店长确认' : '这份服务暂不能更改技师') : profiles.some(available) ? '这位技师目前不能点名此项目。' : '这个项目由门店安排技师。')
    : offersNamedService && canEdit ? '可按项目点名' : offersNamedService ? '当前选单仅可查看' : '暂不能线上点名');

  const tags = Array.from(new Set(peers.flatMap(p => p.tags)));
  const activeTag = tags.includes(styleFilter) ? styleFilter : '';
  const shown = activeTag ? peers.filter(p => p.tags.includes(activeTag)) : peers;
  const shownRequestCount = shown.filter(p => inProject ? available(p) : p.requestable_project_ids.length > 0).length;
  const byNumber = (p: PublicTechnician) => p.technician_id === null && /^\d+\s*号技师$/.test(p.label);
  const separateNamedRoster = profiles.some(p => byNumber(p) && p.portrait_url) && profiles.some(p => p.technician_id !== null);
  const directoryCount = separateNamedRoster ? `共 ${shown.length} 份技师资料` : `共 ${shown.length} 位技师`;
  let directoryGroups = [{ title: '', rows: shown }];
  if (inProject && requestCount > 0 && requestCount < peers.length) {
    directoryGroups = [{ title: '本项目可点名', rows: shown.filter(available) }, { title: '其他技师', rows: shown.filter(p => !available(p)) }];
  } else if (separateNamedRoster) {
    directoryGroups = [{ title: '按工号看照片', rows: shown.filter(byNumber) }, { title: '按姓名找技师', rows: shown.filter(p => !byNumber(p)) }];
  }
  const cardPhoto = (p: PublicTechnician): CardPhoto | undefined => {
    if (hasPortrait(p)) return { url: p.portrait_url, kind: 'portrait' };
    const scene = p.photos.find(item => item.url && !failedImages.includes(item.url));
    if (scene) return { url: scene.url, kind: 'work' };
  };
  const renderCard = (p: PublicTechnician) => {
    const canRequest = inProject ? available(p) : p.requestable_project_ids.length > 0;
    const requestLabel = canRequest ? (inProject ? '可点名' : '可按项目点名') : '门店安排';
    const firstService = !inProject && projects.find(item => p.project_ids.includes(item.id));
    return <DirectoryCard key={p.key} person={p} photo={cardPhoto(p)} canRequest={canRequest}
      projectName={firstService ? displayProjectName(firstService) : undefined}
      requestLabel={requestCount ? requestLabel : ''}
      onOpen={() => {
        listPosition.current = listScroll.current?.scrollTop ?? 0;
        navigate({...view, profile: p.key, photo: undefined, directoryTag: activeTag, directoryTop: listPosition.current});
      }}
      onPhotoError={markFailed} />;
  };
  const storeName = store?.name.replace(/^荷小悦[-·]?/, '') || '荷小悦草本泡脚';
  const venue = storeName.replace(/^(?:荷小悦\s*[-·]?\s*)?草本泡脚[（(]([^（）()]+)[）)]$/, '$1');
  return <dialog className="technician-showcase" ref={dialog} aria-labelledby="technician-title"
    onCancel={event => { event.preventDefault(); back(); }}
    onKeyDown={event => {
      if (event.key !== 'Escape') return;
      // The underlying project also listens for Escape during its exit animation.
      event.preventDefault();
      event.stopPropagation();
      back();
    }}>
    <header className="technician-directory-head">
      <button type="button" className="technician-directory-back" onClick={back} aria-label="返回上一页"><ChevronLeft size={23} /></button>
      <p className="technician-venue" title={storeName}><MapPin size={14} aria-hidden="true" />{venue}</p>
      <h1 id="technician-title">本店技师</h1>
    </header>
    {status !== 'ready' ? <div className="technician-message" role="status">{status === 'loading' ? '正在加载技师资料…' :
      <><p>技师资料暂时打不开</p><button type="button" onClick={() => setAttempt(n => n + 1)}>重新加载</button></>}</div> :
      <>
        <div ref={listScroll} className="technician-scroll technician-directory">
          {peers.length ? <>
            <div className="technician-directory-context">
              <p>{project && <strong>{displayProjectName(project)}</strong>}<span>{directoryCount}</span></p>
              <span>{shownRequestCount === 0 ? '由门店安排' : inProject ? `${shownRequestCount} 位可点名` : '点名由店长确认'}</span>
            </div>
            {tags.length > 0 && <div className="technician-filters" role="group" aria-label="按服务风格筛选">
              {['', ...tags].map(tag => <button key={tag} type="button" aria-pressed={activeTag === tag}
                onClick={() => setStyleFilter(tag)}>{tag || '全部'}</button>)}
            </div>}
            <div className="technician-list">{directoryGroups.filter(group => group.rows.length > 0).map(group => {
              const photographed = group.rows.filter(cardPhoto).sort((a, b) => Number(hasPortrait(b)) - Number(hasPortrait(a)));
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
        {view.profile && <TechnicianPhotoSheet person={person} venue={venue} photoIndex={view.photo}
          failedImages={failedImages} onImageError={markFailed} showPhoto={openPhoto} back={back}
          footer={<footer className="technician-dock">
            <div className="technician-dock-note" role="status">
              <strong>{checking ? '正在确认…' : notice || (inProject ? (project ? displayProjectName(project) : '本份服务') :
                offersNamedService ? (canEdit ? '可申请点名' : '当前选单仅可查看') : '由门店安排')}</strong>
              {!checking && !notice && (inProject ? <small>{statusText}</small> : offersNamedService && canEdit && <small>由店长确认安排</small>)}
            </div>
            {inProject && person && project && canEdit && available(person)
              ? <button type="button" className="technician-primary" onClick={() => void requestPerson(project)} disabled={checking}><Check size={16} />本份服务点名</button>
              : !inProject && offersNamedService && canEdit
                ? <button type="button" className="technician-primary" onClick={() => {
                    const first = servicesSection.current?.querySelector<HTMLButtonElement>('button[data-nameable]');
                    servicesSection.current?.scrollIntoView({block: 'start'});
                    first?.focus({preventScroll: true});
                  }}>选项目点名<ChevronRight size={16} /></button>
                : <button type="button" className="technician-secondary" onClick={inProject ? finish : back}>{inProject ? '返回当前项目' : '返回看技师'}</button>}
          </footer>}>
          {person && <>
            {(person.tags.length > 0 || person.introduction) && <section className="technician-section technician-style" aria-label="服务风格">
              <header className="technician-section-head"><h2>{person.tags.length ? '服务风格' : '个人介绍'}</h2>
                {person.tags.length > 0 && <ul className="technician-tags">{person.tags.map(tag => <li key={tag}>{tag}</li>)}</ul>}</header>
              {person.introduction && <p className="technician-intro">{person.introduction}</p>}
            </section>}
            {services.length > 0 && <section ref={servicesSection} className="technician-section"><header className="technician-section-head"><h2>{!inProject && offersNamedService && canEdit ? '可点项目' : '服务项目'}</h2>
                {services.some(p => p.prices.some(price => price.price_type === 'store')) && <small>门店价</small>}</header><ul className="technician-services">{services.map(p => {
              const price = p.prices.find(v => v.price_type === 'store')?.amount_cents;
              const named = canEdit && Boolean(person.technician_id) && person.requestable_project_ids.includes(p.id);
              const image = projectImage(p);
              const line = <>{!failedImages.includes(image) && <img className="technician-service-thumb" alt="" src={image} loading="lazy" onError={() => markFailed(image)} />}<span><b>{displayProjectName(p)}</b>{p.duration_min != null && <small>{p.duration_min} 分钟</small>}</span>
                <span className="technician-service-choice">{price != null && <strong>{formatMoney(price)}</strong>}
                  {!inProject && <small>{named ? '选项目并点名' : '查看项目'}<ChevronRight size={14} aria-hidden="true" /></small>}
                </span></>;
              return <li key={p.id}>{inProject ? <div>{line}</div> : <button type="button" data-nameable={named || undefined} disabled={checking}
                onClick={() => named ? void requestPerson(p) : onProject(p)}>{line}</button>}</li>;
            })}</ul></section>}
            {!inProject && !offersNamedService && <section className="technician-section technician-assignment" aria-label="点名方式">
              <p>{contactUrl ? '想点这位技师，可先向门店询问今天的安排。' : '想点这位技师，到店时可请前台确认。'}</p>
              {contactUrl && <a className="technician-contact" href={contactUrl} target="_blank" rel="noopener noreferrer">联系本店企微<ChevronRight size={14} aria-hidden="true" /></a>}
            </section>}
            {store && <StoreVisit key={store.id} store={store} />}
          </>}
        </TechnicianPhotoSheet>}
      </>}
    {directoryFooter && <div className="technician-directory-foot">{directoryFooter}</div>}
  </dialog>;
}

import { Check, ChevronLeft, ChevronRight, Clipboard, Clock3, Expand, Images, MapPin, Store, X } from 'lucide-react';
import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { getStoreTechnicians, selectableTechnicians, type PublicTechnician, type SelectableTechnician, type StoreSummary } from '../api';
import { assetPath, displayProjectName, formatMoney, projectImage, type Project } from '../domain';
import type { TechnicianView } from '../technicianNavigation';
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

type CardPhoto = { url: string; kind: 'portrait' | 'work' | 'illustration' };
const illustrationUrls = Array.from({ length: 6 }, (_, i) => assetPath(`technician-illustration-${i + 1}-v1.webp`));
const illustrationCaption = 'AI 示意 · 非本人';

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
  const caption = photo?.kind === 'illustration' ? illustrationCaption : photo?.kind === 'work' ? '服务现场' : '';
  return <li>
    <button type="button" className="technician-card" data-profile={person.key} onClick={onOpen}
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
  if (!store.address && !store.business_hours) return null;
  const copyAddress = async () => {
    try {
      await navigator.clipboard.writeText(store.address);
      setCopyStatus('copied');
    } catch {
      setCopyStatus('manual');
    }
  };
  return <section className="technician-section technician-visit" aria-label="到店信息">
    <h2>到店信息</h2>
    <dl>
      {store.business_hours && <div><dt><Clock3 size={16} aria-hidden="true" />营业时间</dt><dd>{store.business_hours}</dd></div>}
      {store.address && <div><dt><MapPin size={16} aria-hidden="true" />门店地址</dt>
        <dd><span className="technician-address">{store.address}</span>
          <button type="button" onClick={() => void copyAddress()} aria-label="复制门店地址"><Clipboard size={14} aria-hidden="true" />复制地址</button>
          {copyStatus !== 'idle' && <small role="status">{copyStatus === 'copied' ? '地址已复制' : '请选中上方地址复制'}</small>}
        </dd></div>}
    </dl>
  </section>;
}

export default function TechnicianShowcase({ view, store, projects, canEdit, navigate, back, finish, onProject, onRequest, directoryFooter }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const detailScroll = useRef<HTMLDivElement>(null);
  const listScroll = useRef<HTMLDivElement>(null);
  const lastProfile = useRef<string>();
  const profileHeading = useRef<HTMLHeadingElement>(null);
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
  const services = person ? projects.filter(p => person.project_ids.includes(p.id)) : [];
  const hasPortrait = (p: PublicTechnician) => Boolean(p.portrait_url && !failedImages.includes(p.portrait_url));
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
  }, [view.profile, view.projectId, view.photo, canEdit]);
  useEffect(() => {
    if (person && view.photo === undefined) profileHeading.current?.focus({ preventScroll: true });
  }, [person?.key, view.photo]);

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

  const offersNamedService = person && services.some(service => person.requestable_project_ids.includes(service.id));
  const statusText = person && (inProject
    ? (available(person) ? (canEdit ? '点名由店长确认' : '这份服务暂不能更改技师') : profiles.some(available) ? '这位技师目前不能点名此项目。' : '这个项目由门店安排技师。')
    : offersNamedService && canEdit ? '可按项目点名' : offersNamedService ? '当前选单仅可查看' : '由门店安排');

  const directoryGroups = inProject && requestCount > 0 && requestCount < peers.length
    ? [{ title: '本项目可点名', rows: peers.filter(available) }, { title: '其他技师', rows: peers.filter(p => !available(p)) }]
    : [{ title: '', rows: peers }];
  // Use the original roster order even when project eligibility moves cards between groups.
  const illustrations = new Map(profiles.map((p, index) => [p.key, illustrationUrls[index % illustrationUrls.length]]));
  const cardPhoto = (p: PublicTechnician): CardPhoto | undefined => {
    if (hasPortrait(p)) return { url: p.portrait_url, kind: 'portrait' };
    const scene = p.photos.find(item => !failedImages.includes(item.url));
    if (scene) return { url: scene.url, kind: 'work' };
    const illustration = illustrations.get(p.key);
    if (illustration && !failedImages.includes(illustration)) return { url: illustration, kind: 'illustration' };
  };
  const detailPhoto = person && cardPhoto(person);
  const detailMedia = detailPhoto && <>
    <img src={detailPhoto.url} alt={detailPhoto.kind === 'portrait' ? person?.label + '的工作肖像' : ''}
      onError={() => markFailed(detailPhoto.url)} />
    {detailPhoto.kind !== 'portrait' && <span className="technician-photo-caption">
      {detailPhoto.kind === 'illustration' ? illustrationCaption : '服务现场'}
    </span>}
  </>;
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
  const storeName = store?.name.replace(/^荷小悦[-·]?/, '') || '荷小悦草本泡脚';
  const venue = storeName.replace(/^(?:荷小悦\s*[-·]?\s*)?草本泡脚[（(]([^（）()]+)[）)]$/, '$1');
  return <dialog className={'technician-showcase' + (view.profile ? ' technician-profile-page' : '')} ref={dialog} aria-labelledby="technician-title"
    onCancel={event => { event.preventDefault(); back(); }}
    onKeyDown={event => {
      if (event.key !== 'Escape') return;
      // The underlying project also listens for Escape during its exit animation.
      event.preventDefault();
      event.stopPropagation();
      back();
    }}>
    {view.profile ? <header className="mini-detail-nav technician-nav">
      <button type="button" className="technician-back-link" onClick={back} aria-label={photo ? '返回技师主页' : '返回本店技师'}>
        {photo ? <X size={21} /> : <><ChevronLeft size={19} />技师列表</>}
      </button>
      <strong id="technician-title">{photo ? '工作相册' : '技师主页'}</strong>
      {photo && <span title={storeName}>{venue}</span>}
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
              <span>{requestCount === 0 ? '由门店安排' : inProject ? `${requestCount} 位可点名` : '点名由店长确认'}</span>
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
            <section className={'technician-identity' + (detailPhoto ? ' has-photo' : '')}>
              <div className="technician-person">
                {store && <p className="technician-home-store"><MapPin size={14} aria-hidden="true" />{venue}</p>}
                <h1 ref={profileHeading} tabIndex={-1} aria-label={person.label}><TechnicianName label={person.label} /></h1>
                {person.experience && <p className="technician-experience"><Tenure value={person.experience} /></p>}
              </div>
              {detailPhoto && (detailPhoto.kind === 'illustration'
                ? <div className="technician-portrait">{detailMedia}</div>
                : <button type="button" className="technician-portrait"
                    onClick={() => openPhoto(photos.findIndex(p => p.url === detailPhoto.url))}
                    aria-label={detailPhoto.kind === 'portrait' ? '放大' + person.label + '的肖像' : '放大服务现场照片'}>
                    {detailMedia}<Expand size={16} aria-hidden="true" />
                  </button>)}
            </section>
            {!inProject && <section className="technician-assignment" aria-label="点名方式">
              <span className="technician-assignment-icon" aria-hidden="true">{offersNamedService && canEdit ? <Check size={19} /> : <Store size={19} />}</span>
              <div><h2>{statusText}</h2>
                <p>{offersNamedService
                  ? (canEdit ? '选择下方可点名的项目，提交后由店长确认。' : '可浏览这位技师的服务项目。')
                  : '想选这位技师，可到店询问前台。'}</p>
              </div>
            </section>}
            {(person.tags.length > 0 || person.introduction) && <section className="technician-section">
              <h2>{person.introduction ? '个人介绍' : '服务风格'}</h2>
              {person.tags.length > 0 && <ul className="technician-tags" aria-label="服务风格">{person.tags.map(tag => <li key={tag}>{tag}</li>)}</ul>}
              {person.introduction && <p className="technician-intro">{person.introduction}</p>}
            </section>}
            {services.length > 0 && <section className="technician-section"><h2>可做项目</h2><ul className="technician-services">{services.map(p => {
              const price = p.prices.find(v => v.price_type === 'store')?.amount_cents;
              const named = canEdit && Boolean(person.technician_id) && person.requestable_project_ids.includes(p.id);
              const image = projectImage(p);
              const line = <>{!failedImages.includes(image) && <img className="technician-service-thumb" alt="" src={image} loading="lazy" onError={() => markFailed(image)} />}<span><b>{displayProjectName(p)}</b>{p.duration_min != null && <small>{p.duration_min} 分钟</small>}</span>
                <span className="technician-service-choice">{price != null && <strong>{formatMoney(price)}</strong>}
                  {!inProject && <small>{named ? '选项目并点名' : '查看项目'}<ChevronRight size={14} aria-hidden="true" /></small>}
                </span></>;
              return <li key={p.id}>{inProject ? <div>{line}</div> : <button type="button" disabled={checking}
                onClick={() => named ? void requestPerson(p) : onProject(p)}>{line}</button>}</li>;
            })}</ul></section>}
            {person.photos.some(item => !failedImages.includes(item.url)) && <section className="technician-section"><h2><Images size={19} />服务现场</h2>
              <div className="technician-photos">{person.photos.map((picture, i) => !failedImages.includes(picture.url) &&
                <button type="button" key={picture.url} onClick={() => openPhoto(i + Number(Boolean(person.portrait_url)))}><img src={picture.url} alt="" loading="lazy" onError={() => markFailed(picture.url)} /><span>{picture.caption}</span></button>)}</div>
            </section>}
            {store && <StoreVisit key={store.id} store={store} />}
          </div>
          {!inProject && (notice || checking) && <p className="technician-request-notice" role="status">
            {checking ? '正在确认能否点名…' : notice}
          </p>}
          {inProject && <footer className="technician-dock">
            <p role="status">{project && <strong>{displayProjectName(project)} · </strong>}{notice || statusText}</p>
            {canEdit && project && available(person)
              ? <button type="button" className="technician-primary" onClick={() => void requestPerson(project)} disabled={checking}><Check size={17} />{checking ? '确认中…' : '本份服务点名'}</button>
              : <button type="button" className="technician-secondary" onClick={finish}>返回当前项目</button>}
          </footer>}
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

import {
  AlertCircle,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleUserRound,
  Clock3,
  LocateFixed,
  ListChecks,
  MapPinned,
  MessageSquareText,
  Plus,
  RefreshCw,
  ShoppingBag,
  Sofa,
  Sparkles,
  WifiOff,
} from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { useEffect, useMemo, useRef, useState } from 'react';

import {
  ApiError,
  bindSelectionCustomer,
  createEntrySession,
  getAddons,
  getCouponTemplates,
  getCurrentCustomer,
  getPageContent,
  getProjects,
  getSelectionSession,
  getServiceStatus,
  getServicePositionMap,
  moveOccupancy,
  quoteSelectionSession,
  saveSelectionSession,
  submitSelectionRevision,
  submitFeedback,
  type CouponTemplate,
  type Occupancy,
  type SelectionSession,
  type ServiceStatus,
  type ServicePosition,
  type PageContent,
  type SavingHint,
} from './api';
import CouponLoginDialog from './components/CouponLoginDialog';
import FeedbackDialog from './components/FeedbackDialog';
import MembershipDetailPage, { type MembershipKind } from './components/MembershipDetailPage';
import ProfilePage from './components/ProfilePage';
import RecordLoginDialog from './components/RecordLoginDialog';
import SavingHintDialog from './components/SavingHintDialog';
import SelectionSummarySheet from './components/SelectionSummarySheet';
import { authFailureAction, clearCustomerAuth, readCustomerAuth, shouldOfferRecordBinding, writeCustomerAuth, type CustomerAuth } from './customerAuth';
import { customerPageSubtitle, selectionPriceDisplay, serviceFeedbackAction, shouldShowMembershipPromos } from './customerCopy';
import { customerServiceProgress, shouldPollCustomerServiceStatus } from './customerServiceStatus';
import ProjectDetailPage from './components/ProjectDetailPage';
import LocalDetailPage from './components/LocalDetailPage';
import {
  createOverlayGuardState,
  createOverlayHistoryState,
  createOverlayRootState,
  isOverlayGuardState,
  isOverlayRootState,
  readOverlayHistoryStack,
  replaceOverlayHistoryState,
  shouldRunDeferredSwipeBack,
  type OverlayHistoryKind,
} from './overlayHistory';
import { getEntrySource, getPositionSelectionDecision, resolveActivePositionCode, resolveEntryConflict, resolveRequestedPosition, shouldResumeCurrentPosition } from './positionSelection';
import { detailMotion, fadeInMotion, sheetMotion, toastMotion } from './motionPresets';
import SeatMapDialog from './components/SeatMapDialog';
import TeaDetailPage from './components/TeaDetailPage';
import { canEditSelection, expiredSelectionCopy, shouldPreserveOccupancyAfterRevision } from './selectionFlow';
import { isEdgeSwipeBack, shouldReturnToProjectListFromSubmittedScreen } from './swipeBack';
import { shouldHydrateStoredSelection, shouldRestartStoredEntry } from './submittedSelectionRestore';
import { createDiyPageTracking } from './pageTracking';
import {
  activePromotion,
  buildSelectionSummary,
  changeSelectionQuantity,
  emptySelectionDraft,
  removeSelectionEntry,
  type SelectionDraft,
  type SelectionTarget,
} from './selectionSummary';
import {
  flushDiyTracking,
  setDiyTrackingContext,
  trackDiyEvent,
} from './tracking';
import {
  CATALOG_SECTIONS,
  KIOSK_UNBOUND_COPY,
  TEA_SERVICE,
  buildSelectionItems,
  mergeSubmittedSelectionItems,
  calculatePreviewPricing,
  displayPayableTotal,
  resolveMemberTotalCents,
  resolveStoreTotalCents,
  customerProjectHighlights,
  customerProjectSummaryTags,
  customerProjectPurchaseTags,
  customerProjectDisplayTagGroups,
  customerProjectSummaryText,
  displayProjectName,
  featuredProjects,
  formatMoney,
  isDetailOnlyProject,
  isPrimaryFootBathDiy,
  priceGuidance,
  projectListPricePresentation,
  projectImage,
  requiresStaffKioskBinding,
  replaceTea,
  shouldClearDeviceSessionAfterSubmit,
  type Project,
  type Addon,
} from './domain';

type BootState = 'loading' | 'pick-position' | 'ready' | 'occupied' | 'expired' | 'kiosk-unbound' | 'submitted' | 'error';

type EntryRecord = {
  storeId: number;
  positionCode: string;
  accessToken: string;
  session: SelectionSession;
  occupancy: Occupancy;
  position: ServicePosition;
  draftClearedAfterSubmit?: boolean;
};

const pageTracking = createDiyPageTracking(trackDiyEvent);

function getQueryConfig() {
  const query = new URLSearchParams(window.location.search);
  return {
    storeId: Number(query.get('store') || 1),
    positionCode: query.get('seat') || '',
    source: query.get('source') || '',
    qrToken: query.get('qr') || '',
    sessionId: query.get('session') || '',
    accessToken: query.get('token') || '',
  };
}

function storageKey(storeId: number, positionCode: string) {
  return `hxy_diy_entry_${storeId}_${positionCode}`;
}

function readRecord(storeId: number, positionCode: string): EntryRecord | null {
  try {
    return JSON.parse(localStorage.getItem(storageKey(storeId, positionCode)) || 'null') as EntryRecord | null;
  } catch {
    return null;
  }
}

function writeRecord(record: EntryRecord) {
  localStorage.setItem(storageKey(record.storeId, record.positionCode), JSON.stringify(record));
}

function clearRecord(storeId: number, positionCode: string) {
  localStorage.removeItem(storageKey(storeId, positionCode));
}

function deviceLabel() {
  return window.matchMedia('(min-width: 768px)').matches ? '门店平板' : '顾客手机';
}

function formatCountdown(seconds: number) {
  const safe = Math.max(0, seconds);
  return `${String(Math.floor(safe / 60)).padStart(2, '0')}:${String(safe % 60).padStart(2, '0')}`;
}

function InitialPositionPicker({ positions, onSelect, onBlocked, busy, message }: {
  positions: ServicePosition[];
  onSelect: (position: ServicePosition) => void;
  onBlocked: (message: string) => void;
  busy: boolean;
  message: string;
}) {
  const sofas = positions
    .filter((position) => position.type === 'sofa')
    .sort((left, right) => left.sort_order - right.sort_order);
  const leftSofas = sofas.filter((_, index) => index % 2 === 0);
  const rightSofas = sofas.filter((_, index) => index % 2 === 1);

  const renderSeat = (position: ServicePosition) => {
    const decision = getPositionSelectionDecision(position, { mode: 'entry', moving: busy });
    return (
      <button
        key={position.id}
        type="button"
        className={`initial-seat state-${position.state} ${decision.selectable ? '' : 'is-disabled'}`}
        aria-disabled={!decision.selectable}
        onClick={() => decision.selectable ? onSelect(position) : onBlocked(decision.reason)}
      >
        <Sofa size={25} />
        <strong>{position.customer_label}</strong>
        <small>{decision.label}</small>
      </button>
    );
  };

  return (
    <main className="entry-screen">
      <div className="entry-brand"><span>荷</span><strong>荷小悦</strong></div>
      <section className="entry-panel">
        <span className="eyebrow">到店服务选单</span>
        <h1>选择您所在的沙发</h1>
        <p>请按现场号码选择，二维码到店后会自动绑定对应位置。</p>
        {message && <div className="entry-position-notice" role="status">{message}</div>}
        <div className="initial-seat-plan" aria-label="沙发服务区平面布局">
          <div className="initial-entrance-lane" aria-label="门口">
            <div className="initial-entrance">
              <span>门口</span>
            </div>
          </div>
          <div className="initial-seat-column" aria-label="左侧沙发区">{leftSofas.map(renderSeat)}</div>
          <div className="initial-walkway" aria-label="展示柜"><span>展示柜</span></div>
          <div className="initial-seat-column" aria-label="右侧沙发区">{rightSofas.map(renderSeat)}</div>
        </div>
      </section>
    </main>
  );
}

function ProjectPrice({ project, auth }: {
  project: Project;
  auth: { is_member: boolean } | null;
}) {
  const price = projectListPricePresentation(project, auth);
  return (
    <div className="project-meta">
      <div className={auth?.is_member ? 'member-active' : ''}>
        <strong>{price.primaryPrefix && <small>{price.primaryPrefix}</small>}{formatMoney(price.primaryCents)}</strong>
        {price.secondaryStrikethrough
          ? <del>{formatMoney(price.secondaryCents)}</del>
          : <span className="member-price"><small>{price.secondaryPrefix}</small>{formatMoney(price.secondaryCents)}</span>}
      </div>
    </div>
  );
}

function StatusScreen({ type, title, message, onRetry }: {
  type: 'occupied' | 'expired' | 'error';
  title: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <main className="status-screen">
      <div className={`status-symbol ${type}`}>
        {type === 'occupied' ? <Sofa size={34} /> : type === 'expired' ? <Clock3 size={34} /> : <AlertCircle size={34} />}
      </div>
      <span className="eyebrow">荷小悦到店服务</span>
      <h1>{title}</h1>
      <p>{message}</p>
      {onRetry && <button className="primary-action" type="button" onClick={onRetry}><RefreshCw size={18} />重新检查</button>}
      {type === 'occupied' && <small className="status-help">若您就在此位置，请联系前台确认并释放上一次记录。</small>}
    </main>
  );
}

export default function App() {
  const query = useMemo(getQueryConfig, []);
  const booted = useRef(false);
  const entryTracked = useRef(false);
  const hydrated = useRef(false);
  const [boot, setBoot] = useState<BootState>('loading');
  const [bootMessage, setBootMessage] = useState('正在连接门店服务');
  const [projects, setProjects] = useState<Project[]>([]);
  const [addons, setAddons] = useState<Addon[]>([]);
  const [couponTemplates, setCouponTemplates] = useState<CouponTemplate[]>([]);
  const [pageContent, setPageContent] = useState<PageContent | null>(null);
  const [customerAuth, setCustomerAuth] = useState<CustomerAuth | null>(() => readCustomerAuth());
  const [couponLoginOpen, setCouponLoginOpen] = useState(false);
  const [recordLoginOpen, setRecordLoginOpen] = useState(false);
  const [positions, setPositions] = useState<ServicePosition[]>([]);
  const [position, setPosition] = useState<ServicePosition | null>(null);
  const [occupancy, setOccupancy] = useState<Occupancy | null>(null);
  const [session, setSession] = useState<SelectionSession | null>(null);
  const [accessToken, setAccessToken] = useState('');
  const [feedbackToken, setFeedbackToken] = useState('');
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus | null>(null);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const [positionCode, setPositionCode] = useState(query.positionCode);
  const [selectedProjectIds, setSelectedProjectIds] = useState<number[]>([]);
  const [projectPreferences, setProjectPreferences] = useState<Record<number, string[]>>({});
  const [projectAddonIds, setProjectAddonIds] = useState<Record<number, number[]>>({});
  const [projectCatalogSelections, setProjectCatalogSelections] = useState<SelectionDraft['projectCatalogSelections']>({});
  const [localParts, setLocalParts] = useState<string[]>([]);
  const [tea, setTea] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState('tea');
  const catalogMainRef = useRef<HTMLElement | null>(null);
  const sectionScrollTargetRef = useRef<string | null>(null);
  const [detailProject, setDetailProject] = useState<Project | null>(null);
  const [teaDetailOpen, setTeaDetailOpen] = useState(false);
  const [localDetailOpen, setLocalDetailOpen] = useState(false);
  const [seatMapOpen, setSeatMapOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [membershipKind, setMembershipKind] = useState<MembershipKind | null>(null);
  const [moving, setMoving] = useState(false);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [savingHint, setSavingHint] = useState<SavingHint | null>(null);
  const [savingHintOpen, setSavingHintOpen] = useState(false);
  const [selectionSummaryOpen, setSelectionSummaryOpen] = useState(false);
  const [online, setOnline] = useState(navigator.onLine);
  const [toast, setToast] = useState('');
  const [secondsLeft, setSecondsLeft] = useState(600);
  const swipeStart = useRef<{ x: number; y: number } | null>(null);
  const swipeBackTimer = useRef<number | null>(null);

  const activeOverlay: OverlayHistoryKind | null = feedbackOpen ? 'feedback'
    : recordLoginOpen ? 'record-login'
      : couponLoginOpen ? 'coupon-login'
          : savingHintOpen ? 'saving-hint'
            : detailProject ? 'project-detail'
              : localDetailOpen ? 'local-detail'
                : teaDetailOpen ? 'tea-detail'
                  : selectionSummaryOpen ? 'selection-summary'
                    : seatMapOpen ? 'seat-map'
                      : profileOpen ? 'profile'
                        : membershipKind ? 'membership'
                          : null;

  const selectionItems = useMemo(() => buildSelectionItems({
    projects,
    selectedProjectIds,
    projectAddonIds,
    addons,
    projectPreferences,
    projectCatalogSelections,
    localParts,
    tea,
  }), [projects, selectedProjectIds, projectAddonIds, addons, projectPreferences, projectCatalogSelections, localParts, tea]);
  // submitted 会话返回菜单后只保存新增草稿；再次提交时再与服务器原快照合并。
  const submissionItems = useMemo(() => (
    session?.status === 'submitted'
      ? mergeSubmittedSelectionItems(session.items || [], selectionItems)
      : selectionItems
  ), [session?.status, session?.items, selectionItems]);
  const selectionSignature = useMemo(() => JSON.stringify(selectionItems), [selectionItems]);
  const previousSelectionSignature = useRef(selectionSignature);

  useEffect(() => {
    if (previousSelectionSignature.current !== selectionSignature) {
      setSavingHint(null);
      setSavingHintOpen(false);
    }
    previousSelectionSignature.current = selectionSignature;
  }, [selectionSignature]);
  const preview = useMemo(() => calculatePreviewPricing({ projects, selectedProjectIds, projectAddonIds, addons, localParts }), [projects, selectedProjectIds, projectAddonIds, addons, localParts]);
  const appliedPriceType = customerAuth?.user.is_member ? 'member' : 'store';
  const isMember = appliedPriceType === 'member';
  const selectionDraft = useMemo<SelectionDraft>(() => ({
    selectedProjectIds,
    projectPreferences,
    projectAddonIds,
    projectCatalogSelections,
    localParts,
    tea,
  }), [selectedProjectIds, projectPreferences, projectAddonIds, projectCatalogSelections, localParts, tea]);
  const selectionSummary = useMemo(() => buildSelectionSummary({
    projects,
    addons,
    draft: selectionDraft,
    isMember,
  }), [projects, addons, selectionDraft, isMember]);
  const selectionPromotion = useMemo(() => activePromotion(preview, isMember), [preview, isMember]);
  const readOnly = !canEditSelection(session?.status, occupancy?.status);
  const hasSubmittedCustomerSession = session?.status === 'submitted' || session?.status === 'confirmed';
  const serviceProgress = customerServiceProgress(serviceStatus?.occupancy_status ?? occupancy?.status);
  const snapshotMemberTotalCents = resolveMemberTotalCents(
    session?.pricing_snapshot,
    session?.member_total_cents,
  );
  const snapshotStoreTotalCents = resolveStoreTotalCents(
    session?.pricing_snapshot,
    session?.store_total_cents,
  );
  const serverPayableTotal = appliedPriceType === 'member'
    ? snapshotMemberTotalCents
    : snapshotStoreTotalCents;
  const payableTotal = displayPayableTotal({
    readOnly,
    serverTotalCents: Number.isFinite(serverPayableTotal) ? serverPayableTotal : null,
    previewStoreTotalCents: preview.storeTotalCents,
    previewMemberTotalCents: preview.memberTotalCents,
    priceType: appliedPriceType,
  });
  const memberTotalCents = readOnly
    ? snapshotMemberTotalCents
    : preview.memberTotalCents;
  const storeTotalCents = readOnly
    ? snapshotStoreTotalCents
    : preview.storeTotalCents;
  const alignedMemberTotalCents = savingHint?.kind === 'member' && Number.isFinite(savingHint.estimated_saving_cents)
    ? Math.max(0, payableTotal - Number(savingHint.estimated_saving_cents))
    : memberTotalCents;
  const priceDisplay = selectionPriceDisplay(isMember, payableTotal, alignedMemberTotalCents, storeTotalCents);
  const serviceDurationMinutes = (item: SelectionSession['items'][number]): number => {
    const projectDuration = projects.find((project) => String(project.id) === String(item.project_id))?.duration_min || 0;
    const addonDuration = (item.addon_ids || []).reduce((total, addonId) => total + (addons.find((addon) => addon.id === addonId)?.duration_min || 0), 0);
    return (projectDuration + addonDuration) * Math.max(1, item.quantity || 1);
  };
  const totalServiceMinutes = session?.items.filter((item) => item.item_type === 'service').reduce((total, item) => total + serviceDurationMinutes(item), 0) || 0;
  const localProject = projects.find((project) => project.category === 'local-strength');
  const hasChargeableService = selectedProjectIds.length > 0 || localParts.length > 0;
  const selectedCount = selectionSummary.totalCount;
  const featuredCoupon = couponTemplates.find((coupon) => coupon.claimable) || couponTemplates[0] || null;
  const featured = featuredProjects(projects);

  const flash = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(''), 2400);
  };

  const applyOverlayHistoryState = (stack: OverlayHistoryKind[]) => {
    const includes = (overlay: OverlayHistoryKind) => stack.includes(overlay);
    setFeedbackOpen(includes('feedback'));
    setRecordLoginOpen(includes('record-login'));
    setCouponLoginOpen(includes('coupon-login'));
    setSavingHintOpen(includes('saving-hint'));
    setSelectionSummaryOpen(includes('selection-summary'));
    setDetailProject((current) => includes('project-detail') ? current : null);
    setLocalDetailOpen(includes('local-detail'));
    setTeaDetailOpen(includes('tea-detail'));
    setSeatMapOpen(includes('seat-map'));
    setProfileOpen(includes('profile'));
    setMembershipKind((current) => includes('membership') ? current : null);
  };

  const openOverlay = (overlay: OverlayHistoryKind) => {
    if (activeOverlay === overlay) return;
    const nextState = createOverlayHistoryState(window.history.state, overlay);
    window.history.pushState(nextState, '', window.location.href);
  };

  const replaceTopOverlay = (overlay: OverlayHistoryKind) => {
    const nextState = replaceOverlayHistoryState(window.history.state, overlay);
    window.history.replaceState(nextState, '', window.location.href);
  };

  const dismissTopOverlay = () => {
    if (activeOverlay && readOverlayHistoryStack(window.history.state).length > 0) {
      window.history.back();
      return;
    }
    applyOverlayHistoryState([]);
  };

  const openProjectDetail = (project: Project) => {
    pageTracking.projectView({
      project_id: project.id,
      project_code: project.code,
      project_name: project.name,
    });
    setDetailProject(project);
    openOverlay('project-detail');
  };

  const openTeaDetail = () => {
    setTeaDetailOpen(true);
    openOverlay('tea-detail');
  };

  const openLocalDetail = () => {
    setLocalDetailOpen(true);
    openOverlay('local-detail');
  };

  const openSelectionSummary = () => {
    setSelectionSummaryOpen(true);
    openOverlay('selection-summary');
  };

  const handleSummaryModify = (target: SelectionTarget) => {
    if (readOnly) return;
    if (target.kind === 'project' || target.kind === 'addon') {
      const projectId = target.projectId;
      const project = projects.find((item) => item.id === projectId);
      if (project) openProjectDetail(project);
      else flash('这个项目暂时无法修改，请刷新后重试');
      return;
    }
    if (target.kind === 'local') {
      openLocalDetail();
      return;
    }
    openTeaDetail();
  };

  const handleSummaryRemove = (target: SelectionTarget) => {
    if (readOnly) return;
    const next = removeSelectionEntry(selectionDraft, target);
    setSelectedProjectIds(next.selectedProjectIds);
    setProjectPreferences(next.projectPreferences);
    setProjectAddonIds(next.projectAddonIds);
    setProjectCatalogSelections(next.projectCatalogSelections || {});
    setLocalParts(next.localParts);
    setTea(next.tea);

    if (target.kind === 'project') {
      const name = projects.find((project) => project.id === target.projectId)?.name || '项目';
      flash(`${name}已删除`);
    } else if (target.kind === 'addon') {
      const name = addons.find((addon) => addon.id === target.addonId)?.name || '加项';
      flash(`${name}已删除`);
    } else if (target.kind === 'local') {
      flash(`${target.part}调理已删除`);
    } else {
      flash('赠饮已删除');
    }
  };

  const handleSummaryQuantityChange = (
    target: Extract<SelectionTarget, { kind: 'project' | 'local' }>,
    delta: 1 | -1,
  ) => {
    if (readOnly) return;
    const next = changeSelectionQuantity(selectionDraft, target, delta);
    setSelectedProjectIds(next.selectedProjectIds);
    setProjectPreferences(next.projectPreferences);
    setProjectAddonIds(next.projectAddonIds);
    setProjectCatalogSelections(next.projectCatalogSelections || projectCatalogSelections);
    setLocalParts(next.localParts);
    setTea(next.tea);
  };

  const startFreshSelectionDraft = () => {
    const empty = emptySelectionDraft();
    setSelectedProjectIds(empty.selectedProjectIds);
    setProjectPreferences(empty.projectPreferences);
    setProjectAddonIds(empty.projectAddonIds);
    setProjectCatalogSelections(empty.projectCatalogSelections || {});
    setLocalParts(empty.localParts);
    setTea(empty.tea);
    setSelectionSummaryOpen(false);
    setSavingHint(null);
    setSavingHintOpen(false);
  };

  const openSeatMap = () => {
    setSeatMapOpen(true);
    openOverlay('seat-map');
  };

  const openProfile = () => {
    setProfileOpen(true);
    openOverlay('profile');
  };

  const openMembership = (kind: MembershipKind) => {
    setMembershipKind(kind);
    openOverlay('membership');
  };

  const openCouponLogin = () => {
    pageTracking.loginPromptView({ prompt_type: 'coupon', trigger: 'project_detail' });
    setCouponLoginOpen(true);
    openOverlay('coupon-login');
  };

  const openRecordLogin = () => {
    pageTracking.loginPromptView({ prompt_type: 'record', trigger: 'service_record' });
    setRecordLoginOpen(true);
    openOverlay('record-login');
  };

  const openFeedback = () => {
    pageTracking.feedbackView({ can_evaluate: Boolean(serviceStatus?.can_evaluate) });
    setFeedbackOpen(true);
    openOverlay('feedback');
  };

  const handleTouchStart = (event: React.TouchEvent<HTMLElement>) => {
    if (swipeBackTimer.current !== null) {
      window.clearTimeout(swipeBackTimer.current);
      swipeBackTimer.current = null;
    }
    const touch = event.touches[0];
    swipeStart.current = touch ? { x: touch.clientX, y: touch.clientY } : null;
  };

  const handleTouchEnd = (event: React.TouchEvent<HTMLElement>) => {
    const start = swipeStart.current;
    const touch = event.changedTouches[0];
    swipeStart.current = null;
    if (start && touch && shouldReturnToProjectListFromSubmittedScreen(
      boot === 'submitted',
      Boolean(activeOverlay),
      { x: start.x, y: start.y },
      { x: touch.clientX, y: touch.clientY },
    )) {
      if (event.cancelable) event.preventDefault();
      returnToProjectListAfterSubmit();
      return;
    }
    if (activeOverlay && start && touch && isEdgeSwipeBack(start, { x: touch.clientX, y: touch.clientY })) {
      if (event.cancelable) event.preventDefault();
      pageTracking.navigationBack({ overlay: activeOverlay, method: 'edge_swipe' });
      const beforeState = window.history.state;
      swipeBackTimer.current = window.setTimeout(() => {
        swipeBackTimer.current = null;
        if (shouldRunDeferredSwipeBack(beforeState, window.history.state)) dismissTopOverlay();
      }, 100);
    }
  };

  const handleTouchCancel = () => {
    swipeStart.current = null;
  };

  const hydrateSelection = (nextSession: SelectionSession) => {
    const selected: number[] = [];
    const prefs: Record<number, string[]> = {};
    const addonSelections: Record<number, number[]> = {};
    const catalogSelections: NonNullable<SelectionDraft['projectCatalogSelections']> = {};
    const parts: string[] = [];
    let selectedTea: string | null = null;
    for (const item of nextSession.items || []) {
      if (item.project_id === 'tea') {
        selectedTea = item.diy_preferences?.[0] || null;
      } else if (item.category === 'local-strength' || item.project_id === 'local-strength') {
        const part = item.diy_preferences?.[0];
        if (part) {
          const quantity = Math.max(1, Number(item.quantity) || 1);
          parts.push(...Array.from({ length: quantity }, () => part));
        }
      } else if (typeof item.project_id === 'number') {
        const quantity = Math.max(1, Number(item.quantity) || 1);
        selected.push(...Array.from({ length: quantity }, () => item.project_id as number));
        prefs[item.project_id] = item.diy_preferences || [];
        if (item.addon_ids?.length) addonSelections[item.project_id] = item.addon_ids;
        if (item.catalog_version_id !== null && item.catalog_version_id !== undefined) {
          catalogSelections[item.project_id] = { projectId: item.project_id, catalogVersionId: item.catalog_version_id, optionChoiceIds: item.option_choice_ids || [] };
        }
      }
    }
    setSelectedProjectIds(selected);
    setProjectPreferences(prefs);
    setProjectAddonIds(addonSelections);
    setProjectCatalogSelections(catalogSelections);
    setLocalParts(parts);
    setTea(selectedTea);
  };

  const persistCurrent = (
    nextSession = session,
    nextOccupancy = occupancy,
    nextPosition = position,
    nextCode = positionCode,
    draftClearedAfterSubmit = false,
  ) => {
    if (!nextSession || !nextOccupancy || !nextPosition || !accessToken || !nextCode) return;
    writeRecord({
      storeId: query.storeId,
      positionCode: nextCode,
      accessToken,
      session: nextSession,
      occupancy: nextOccupancy,
      position: nextPosition,
      draftClearedAfterSubmit,
    });
  };

  const returnToProjectListAfterSubmit = async () => {
    const currentStatus = serviceStatus?.occupancy_status ?? occupancy?.status;
    // 返回浏览不依赖服务位释放或网络；旧订单继续保留用于查看和评价。
    startFreshSelectionDraft();
    persistCurrent(session, occupancy, position, positionCode, true);
    setBoot('ready');
    if (currentStatus === 'post_service_present' || currentStatus === 'cleaning' || currentStatus === 'released') {
      // 服务状态可能先于服务位地图返回，不能让旧 in_service 快照开放历史订单编辑。
      if (occupancy) setOccupancy({ ...occupancy, status: currentStatus });
      try {
        const map = await getServicePositionMap(query.storeId, session?.id, accessToken || undefined);
        setPositions(map.positions);
        const current = resolveRequestedPosition(map.positions, resolveActivePositionCode(positionCode, query.positionCode));
        if (shouldRestartStoredEntry({
          requestedPositionFound: Boolean(current),
          hasActiveOccupancy: Boolean(current?.occupancy),
        })) {
          clearRecord(query.storeId, positionCode);
          await enterPosition(positionCode);
          return;
        }
        flash('可以先浏览项目；再次选购请等待服务位释放，或联系前台');
      } catch {
        flash('暂时无法确认服务位，可先浏览项目，联网后重试');
      }
      return;
    }
  };

  const loadMap = async (nextSession = session, token = accessToken) => {
    const map = await getServicePositionMap(query.storeId, nextSession?.id, token || undefined);
    setPositions(map.positions);
    const current = resolveRequestedPosition(map.positions, resolveActivePositionCode(positionCode, query.positionCode));
    if (current) {
      setPosition(current);
      if (current.occupancy) setOccupancy(current.occupancy);
    }
    return { map, current };
  };

  const enterPosition = async (code: string, recovered = false) => {
    setBoot('loading');
    setBootMessage('正在为您确认服务位');
    try {
      const entry = await createEntrySession({
        store_id: query.storeId,
        position_code: code,
        source: getEntrySource({
          source: query.source,
          qrToken: query.qrToken,
          positionCode: code,
        }),
        device_label: deviceLabel(),
        entry_token: query.qrToken || undefined,
      });
      setAccessToken(entry.access_token);
      setSession(entry.session);
      setServiceStatus(null);
      setOccupancy(entry.occupancy);
      setPosition(entry.position);
      setPositionCode(code);
      hydrateSelection(entry.session);
      const record: EntryRecord = {
        storeId: query.storeId,
        positionCode: code,
        accessToken: entry.access_token,
        session: entry.session,
        occupancy: entry.occupancy,
        position: entry.position,
      };
      writeRecord(record);
      const map = await getServicePositionMap(query.storeId, entry.session.id, entry.access_token);
      setPositions(map.positions);
      const current = resolveRequestedPosition(map.positions, code);
      if (current) {
        setPosition(current);
        if (current.occupancy) setOccupancy(current.occupancy);
      }
      hydrated.current = true;
      setBoot(canEditSelection(entry.session.status, entry.occupancy.status) ? 'ready' : 'submitted');
      if (recovered) flash(`已恢复${entry.position.customer_label}的本次选单`);
    } catch (error) {
      if (error instanceof ApiError) {
        const currentPositionCode = typeof error.detail.current_position_code === 'string'
          ? error.detail.current_position_code
          : undefined;
        const resolution = resolveEntryConflict(error.code, currentPositionCode, error.status);
        if (shouldResumeCurrentPosition({ requestedCode: query.positionCode, qrToken: query.qrToken, conflict: resolution }) && resolution.action === 'resume-current' && resolution.positionCode !== code) {
          const recoveryUrl = new URL(window.location.href);
          recoveryUrl.searchParams.set('seat', resolution.positionCode);
          window.history.replaceState(window.history.state, '', recoveryUrl);
          await enterPosition(resolution.positionCode, true);
          return;
        }
        const canPickAlternative = !query.qrToken && !code.startsWith('room-') && query.source !== 'room_qr' && query.source !== 'kiosk';
        if (resolution.action === 'refresh-map' && canPickAlternative) {
          const refreshed = await getServicePositionMap(query.storeId).catch(() => null);
          if (refreshed) setPositions(refreshed.positions);
          setBootMessage(`${error.message}，沙发状态已刷新`);
          setBoot('pick-position');
          return;
        }
        if (['POSITION_OCCUPIED', 'BROWSER_ACTIVE_ELSEWHERE'].includes(error.code)) {
          setBootMessage(error.message);
          setBoot('occupied');
          return;
        }
      }
      setBootMessage(error instanceof Error ? error.message : '门店服务暂时不可用');
      setBoot('error');
    }
  };

  const initialize = async () => {
    setBoot('loading');
    try {
      const [catalog, addonCatalog, publicMap, coupons, content] = await Promise.all([
        getProjects(query.storeId),
        getAddons(query.storeId).catch(() => []),
        getServicePositionMap(query.storeId),
        getCouponTemplates(customerAuth?.token).catch(() => []),
        getPageContent(query.storeId).catch(() => null),
      ]);
      setProjects(catalog);
      setAddons(addonCatalog);
      setPositions(publicMap.positions);
      setCouponTemplates(coupons);
      setPageContent(content);
      if (query.sessionId && query.accessToken) {
        const linkedSession = await getSelectionSession(query.sessionId, query.accessToken);
        const linkedMap = await getServicePositionMap(query.storeId, linkedSession.id, query.accessToken);
        const linkedRequested = resolveRequestedPosition(linkedMap.positions, query.positionCode);
        const current = linkedRequested?.occupancy
          ? linkedRequested
          : query.positionCode
            ? undefined
            : linkedMap.positions.find((item) => item.is_current && item.occupancy);
        if (!current?.occupancy) throw new Error('共享设备绑定已失效，请前台重新绑定');
        setPositions(linkedMap.positions);
        setAccessToken(query.accessToken);
        setSession(linkedSession);
        setOccupancy(current.occupancy);
        setPosition(current);
        setPositionCode(current.code);
        hydrateSelection(linkedSession);
        writeRecord({
          storeId: query.storeId,
          positionCode: current.code,
          accessToken: query.accessToken,
          session: linkedSession,
          occupancy: current.occupancy,
          position: current,
        });
        const cleanUrl = new URL(window.location.href);
        cleanUrl.searchParams.set('seat', current.code);
        cleanUrl.searchParams.delete('session');
        cleanUrl.searchParams.delete('token');
        window.history.replaceState(window.history.state, '', cleanUrl);
        hydrated.current = true;
        setBoot(canEditSelection(linkedSession.status, current.occupancy.status) ? 'ready' : 'submitted');
        return;
      }
      if (!query.positionCode) {
        setBoot('pick-position');
        return;
      }

      const record = readRecord(query.storeId, query.positionCode);
      if (!record) {
        if (requiresStaffKioskBinding(query.source, false)) {
          setBoot('kiosk-unbound');
          return;
        }
        await enterPosition(query.positionCode);
        return;
      }
      try {
        const restoredSession = await getSelectionSession(record.session.id, record.accessToken);
        if (restoredSession.status === 'cancelled' || restoredSession.status === 'expired') {
          clearRecord(query.storeId, query.positionCode);
          if (requiresStaffKioskBinding(query.source, false)) {
            setBoot('kiosk-unbound');
            return;
          }
          await enterPosition(query.positionCode);
          return;
        }
        setAccessToken(record.accessToken);
        setSession(restoredSession);
        setOccupancy(record.occupancy);
        setPosition(record.position);
        setPositionCode(record.positionCode);
        const map = await getServicePositionMap(query.storeId, restoredSession.id, record.accessToken);
        setPositions(map.positions);
        const current = resolveRequestedPosition(map.positions, query.positionCode || record.positionCode);
        if (shouldRestartStoredEntry({
          requestedPositionFound: Boolean(current),
          hasActiveOccupancy: Boolean(current?.occupancy),
        })) {
          clearRecord(query.storeId, query.positionCode);
          await enterPosition(query.positionCode);
          return;
        }
        if (record.position.type === 'sofa' && !current) {
          clearRecord(query.storeId, query.positionCode);
          await enterPosition(query.positionCode);
          return;
        }
        if (current) {
          setPosition(current);
          if (current.occupancy) setOccupancy(current.occupancy);
        }
        const restoredOccupancyStatus = current?.occupancy?.status || record.occupancy.status;
        if (shouldHydrateStoredSelection({
          draftClearedAfterSubmit: record.draftClearedAfterSubmit,
          sessionStatus: restoredSession.status,
          occupancyStatus: restoredOccupancyStatus,
        })) {
          hydrateSelection(restoredSession);
        } else {
          startFreshSelectionDraft();
        }
        hydrated.current = true;
        setBoot(canEditSelection(restoredSession.status, restoredOccupancyStatus) ? 'ready' : 'submitted');
      } catch {
        clearRecord(query.storeId, query.positionCode);
        if (requiresStaffKioskBinding(query.source, false)) {
          setBoot('kiosk-unbound');
          return;
        }
        await enterPosition(query.positionCode);
      }
    } catch (error) {
      setBootMessage(error instanceof Error ? error.message : '门店服务暂时不可用');
      setBoot('error');
    }
  };

  const handleCouponSuccess = (auth: CustomerAuth, message: string) => {
    setCustomerAuth(auth);
    dismissTopOverlay();
    flash(message);
    void getCouponTemplates(auth.token).then(setCouponTemplates).catch(() => undefined);
    if (session && accessToken) {
      void getSelectionSession(session.id, accessToken).then(setSession).catch(() => undefined);
    }
  };

  const refreshAfterCustomerLogin = (auth: CustomerAuth, message: string) => {
    setCustomerAuth(auth);
    if (!session || !accessToken) {
      flash(message);
      return;
    }
    void getSelectionSession(session.id, accessToken)
      .then((updated) => {
        setSession(updated);
        flash(auth.user.is_member ? '已识别会员身份，会员价已更新' : message);
      })
      .catch(() => flash(message));
  };

  useEffect(() => {
    setDiyTrackingContext({
      store_id: query.storeId,
      selection_session_id: session?.id,
      position_id: position?.id,
      source: session?.source || occupancy?.source || query.source || 'unknown',
      auth_token: customerAuth?.token || '',
    });
  }, [query.storeId, query.source, session?.id, session?.source, position?.id, occupancy?.source, customerAuth?.token]);

  // 后台可以在顾客停留期间开通会员；每次令牌建立/恢复时刷新一次身份快照，
  // 让“我的”、项目价格和选单合计立即使用最新会员状态。
  useEffect(() => {
    const token = customerAuth?.token;
    if (!token) return undefined;
    let active = true;
    void getCurrentCustomer(token)
      .then((user) => {
        if (!active) return;
        setCustomerAuth((current) => {
          if (!current || current.token !== token) return current;
          const refreshed = { ...current, user };
          writeCustomerAuth(refreshed);
          return refreshed;
        });
      })
      .catch((error) => {
        if (active && authFailureAction(error) === 'reauthenticate') {
          clearCustomerAuth();
          setCustomerAuth(null);
          flash('登录状态已更新，请重新登录');
        }
      });
    return () => { active = false; };
  }, [customerAuth?.token]);

  useEffect(() => {
    if (boot === 'loading' || entryTracked.current) return;
    entryTracked.current = true;
    pageTracking.entryView({ entry_state: boot });
    void flushDiyTracking();
  }, [boot]);

  useEffect(() => {
    if (booted.current) return;
    booted.current = true;
    void initialize();
  }, []);

  useEffect(() => {
    if (!isOverlayGuardState(window.history.state)) {
      const rootState = createOverlayRootState(window.history.state);
      window.history.replaceState(rootState, '', window.location.href);
      window.history.pushState(createOverlayGuardState(rootState), '', window.location.href);
    }
    const restoreOverlay = (event: PopStateEvent) => {
      const stack = readOverlayHistoryStack(event.state);
      applyOverlayHistoryState(stack);
      if (stack.length === 0 && isOverlayRootState(event.state) && !isOverlayGuardState(event.state)) {
        window.history.pushState(createOverlayGuardState(event.state), '', window.location.href);
      }
    };
    window.addEventListener('popstate', restoreOverlay);
    return () => window.removeEventListener('popstate', restoreOverlay);
  }, []);

  useEffect(() => {
    if (selectionSummaryOpen && selectedCount === 0) dismissTopOverlay();
  }, [selectionSummaryOpen, selectedCount]);

  useEffect(() => () => {
    if (swipeBackTimer.current !== null) window.clearTimeout(swipeBackTimer.current);
  }, []);

  useEffect(() => {
    const onOnline = () => setOnline(true);
    const onOffline = () => setOnline(false);
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
    };
  }, []);

  useEffect(() => {
    if (boot !== 'ready' || !occupancy?.hold_expires_at) return undefined;
    const tick = () => {
      const remaining = Math.ceil((new Date(occupancy.hold_expires_at!).getTime() - Date.now()) / 1000);
      setSecondsLeft(Math.max(0, remaining));
      if (remaining <= 0) setBoot('expired');
    };
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [boot, occupancy?.hold_expires_at]);

  useEffect(() => {
    if (boot !== 'ready' || !session || session.status !== 'draft' || !accessToken || !hydrated.current) return undefined;
    const timer = window.setTimeout(async () => {
      setSaving(true);
      try {
        const saved = await saveSelectionSession(session.id, accessToken, selectionItems, deviceLabel());
        setSession(saved);
        if (position?.type === 'sofa') {
          const { current } = await loadMap(saved, accessToken);
          if (current?.occupancy) persistCurrent(saved, current.occupancy, current, current.code);
        } else if (occupancy) {
          const refreshed = {
            ...occupancy,
            version: occupancy.version + 1,
            hold_expires_at: new Date(Date.now() + 10 * 60 * 1000).toISOString(),
          };
          setOccupancy(refreshed);
          persistCurrent(saved, refreshed, position);
        }
      } catch (error) {
        if (error instanceof ApiError && error.status === 409) {
          setBoot('expired');
        } else {
          flash('选单暂未同步，网络恢复后请再试');
        }
      } finally {
        setSaving(false);
      }
    }, 500);
    return () => window.clearTimeout(timer);
  }, [selectionSignature]);

  useEffect(() => {
    const canWatchPositionChanges = position?.type === 'sofa'
      && (session?.source || occupancy?.source || query.source) !== 'kiosk'
      && occupancy?.status === 'held';
    if (!seatMapOpen || boot !== 'ready' || !canWatchPositionChanges) return undefined;
    const timer = window.setInterval(() => void loadMap(), 3000);
    return () => window.clearInterval(timer);
  }, [seatMapOpen, boot, position?.type, session?.source, occupancy?.source, occupancy?.status, query.source, session?.id, accessToken]);

  useEffect(() => {
    const token = feedbackToken || accessToken;
    if (!shouldPollCustomerServiceStatus({
      boot,
      hasSession: Boolean(session),
      hasToken: Boolean(token),
      readOnly,
      hasSubmittedService: hasSubmittedCustomerSession,
    }) || !session) return undefined;
    let active = true;
    const refresh = async () => {
      try {
        const status = await getServiceStatus(session.id, token);
        if (!active) return;
        setServiceStatus(status);
      } catch {
        // 评价状态不是选单主流程，暂时不可用时保持当前页面可用。
        return;
      }

      try {
        const [latestSession, map] = await Promise.all([
          getSelectionSession(session.id, token),
          getServicePositionMap(query.storeId, session.id, token),
        ]);
        if (!active) return;
        setSession(latestSession);
        setPositions(map.positions);
        const currentRequested = resolveRequestedPosition(map.positions, resolveActivePositionCode(positionCode, query.positionCode));
        const current = currentRequested?.occupancy
          ? currentRequested
          : query.positionCode || positionCode
            ? undefined
            : map.positions.find((item) => item.is_current && item.occupancy);
        if (current?.occupancy) {
          setPosition(current);
          setOccupancy(current.occupancy);
          const stored = readRecord(query.storeId, positionCode);
          persistCurrent(latestSession, current.occupancy, current, current.code, stored?.draftClearedAfterSubmit ?? false);
        }
      } catch {
        // 状态已更新；会话或服务位同步短暂失败时，下一轮轮询会重试。
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 20000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [boot, session?.id, feedbackToken, accessToken, readOnly, hasSubmittedCustomerSession, positionCode]);

  useEffect(() => {
    if (boot !== 'ready') return undefined;
    const elements = CATALOG_SECTIONS.map((section) => document.getElementById(`section-${section.id}`)).filter(Boolean) as HTMLElement[];
    const catalogMain = catalogMainRef.current;
    if (!catalogMain || !elements.length) return undefined;
    let frame = 0;
    const syncActiveSection = () => {
      frame = 0;
      // 以右侧容器的滚动位置为唯一依据，避免 IntersectionObserver
      // 在短分区交界处按可见比例误判当前分类。
      const anchor = catalogMain.scrollTop + 32;
      let current = elements[0].id.replace('section-', '');
      elements.forEach((element) => {
        if (element.offsetTop <= anchor) current = element.id.replace('section-', '');
      });
      const requestedSection = sectionScrollTargetRef.current;
      const requestedElement = requestedSection ? document.getElementById(`section-${requestedSection}`) : null;
      const maxScrollTop = catalogMain.scrollHeight - catalogMain.clientHeight;
      if (catalogMain.scrollTop >= maxScrollTop - 2) current = elements[elements.length - 1].id.replace('section-', '');
      // 最后一个分区可能因容器到底而无法把标题滚到顶部，此时到达
      // 最大滚动位置即视为命中目标，避免锁定状态阻塞后续手动滚动。
      const requestedAtEnd = Boolean(requestedSection && requestedElement && requestedElement.offsetTop > maxScrollTop && catalogMain.scrollTop >= maxScrollTop - 2);
      if (requestedSection && requestedSection !== current && !requestedAtEnd) return;
      if (requestedAtEnd) current = requestedSection as string;
      if (requestedSection === current) sectionScrollTargetRef.current = null;
      setActiveSection(current);
      document.querySelector<HTMLElement>(`[data-category-id="${current}"]`)?.scrollIntoView({ block: 'nearest' });
    };
    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(syncActiveSection);
    };
    catalogMain.addEventListener('scroll', onScroll, { passive: true });
    syncActiveSection();
    return () => {
      catalogMain.removeEventListener('scroll', onScroll);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [boot, projects.length]);

  const retry = () => {
    hydrated.current = false;
    void initialize();
  };

  const selectInitialPosition = async (next: ServicePosition) => {
    const url = new URL(window.location.href);
    url.searchParams.set('store', String(query.storeId));
    url.searchParams.set('seat', next.code);
    url.searchParams.set('source', 'store_qr');
    window.history.replaceState(window.history.state, '', url);
    setBootMessage('');
    await enterPosition(next.code);
  };

  const selectTea = (nextTea: string) => {
    if (readOnly) return;
    setTea((current) => replaceTea(current, nextTea));
    dismissTopOverlay();
    flash(`${nextTea}已选`);
  };

  const saveLocalParts = (parts: string[]) => {
    if (readOnly) return;
    setLocalParts((current) => [...new Set(parts)].flatMap((part) => {
      const quantity = Math.max(1, current.filter((item) => item === part).length);
      return Array.from({ length: quantity }, () => part);
    }));
    dismissTopOverlay();
    flash(`已选择 ${parts.length} 个局部调理部位`);
  };

  const saveProject = ({ project, preferences, addonIds, localParts: nextLocalParts, catalogVersionId, optionChoiceIds, linkedProjectIds }: {
    project: Project;
    preferences: string[];
    addonIds: number[];
    localParts: string[];
    catalogVersionId?: number;
    optionChoiceIds?: number[];
    linkedProjectIds?: number[];
  }) => {
    if (readOnly) return;
    if (isDetailOnlyProject(project)) {
      dismissTopOverlay();
      return;
    }
    pageTracking.projectConfigSave({
      project_id: project.id,
      preference_count: preferences.length,
      addon_count: addonIds.length,
    });
    setSelectedProjectIds((ids) => [...new Set([...ids, project.id, ...(linkedProjectIds || [])])]);
    setProjectPreferences((current) => ({ ...current, [project.id]: preferences }));
    setProjectAddonIds((current) => ({ ...current, [project.id]: addonIds }));
    setLocalParts(nextLocalParts);
    if (catalogVersionId && optionChoiceIds) {
      setProjectCatalogSelections((current) => ({ ...current, [project.id]: { projectId: project.id, catalogVersionId, optionChoiceIds: [...new Set(optionChoiceIds)] } }));
    }
    dismissTopOverlay();
    flash(`${project.name}配置已保存`);
  };

  const removeProject = (project: Project) => {
    if (readOnly) return;
    setSelectedProjectIds((ids) => ids.filter((id) => id !== project.id));
    setProjectPreferences((current) => {
      const next = { ...current };
      delete next[project.id];
      return next;
    });
    setProjectAddonIds((current) => {
      const next = { ...current };
      delete next[project.id];
      return next;
    });
    setProjectCatalogSelections((current) => {
      const next = { ...current };
      delete next[project.id];
      return next;
    });
    dismissTopOverlay();
    flash(`${project.name}已移出`);
  };

  const handleMove = async (target: ServicePosition) => {
    if (!occupancy || !accessToken || !session || !position) return;
    setMoving(true);
    try {
      const moved = await moveOccupancy(occupancy.id, accessToken, target.id, occupancy.version);
      const movedState: ServicePosition['state'] = moved.status === 'released' ? 'available' : moved.status;
      const nextPosition: ServicePosition = { ...target, is_current: true, state: movedState, occupancy: moved };
      clearRecord(query.storeId, positionCode);
      setOccupancy(moved);
      setPosition(nextPosition);
      setPositionCode(target.code);
      setPositions((items) => items.map((item) => ({
        ...item,
        is_current: item.id === target.id,
        state: item.id === target.id ? movedState : item.id === position.id ? 'available' : item.state,
        occupancy: item.id === target.id ? moved : item.id === position.id ? null : item.occupancy,
      })));
      const url = new URL(window.location.href);
      url.searchParams.set('seat', target.code);
      window.history.replaceState(window.history.state, '', url);
      writeRecord({ storeId: query.storeId, positionCode: target.code, accessToken, session, occupancy: moved, position: nextPosition });
      dismissTopOverlay();
      flash(`已切换到${target.customer_label}`);
    } catch (error) {
      flash(error instanceof Error ? error.message : '换位失败，请刷新重试');
      await loadMap();
    } finally {
      setMoving(false);
    }
  };

  const submitRevision = async () => {
    if (!session || !accessToken) return;
    setSubmitting(true);
    try {
      await submitSelectionRevision(session.id, accessToken, submissionItems, deviceLabel());
      const submitted = await getSelectionSession(session.id, accessToken);
      setSession(submitted);
      setFeedbackToken(accessToken);
      const preserveInService = shouldPreserveOccupancyAfterRevision(occupancy?.status);
      const clearSharedDevice = shouldClearDeviceSessionAfterSubmit(session.source || query.source);
      if (occupancy) {
        const nextOccupancy = preserveInService
          ? occupancy
          : { ...occupancy, status: 'waiting_service' as const, hold_expires_at: null, version: occupancy.version + 1 };
        setOccupancy(nextOccupancy);
        if (clearSharedDevice) clearRecord(query.storeId, positionCode);
        else persistCurrent(submitted, nextOccupancy, position);
      }
      if (clearSharedDevice) setAccessToken('');
      if (preserveInService) {
        flash('加选已提交，等待前台确认');
        setBoot('ready');
      } else {
        setBoot('submitted');
      }
    } catch (error) {
      flash(error instanceof Error ? error.message : '提交失败，请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  const submit = async () => {
    if (!session || !accessToken || submitting) return;
    if (!hasChargeableService) {
      // 仅选择茶饮时允许提交，但先提示顾客补充服务项目。
      const proceed = window.confirm('您还未选择服务项目，本次仅提交免费茶饮。建议先逛逛项目，是否继续提交茶饮？');
      if (!proceed) return;
    }
    setSubmitting(true);
    try {
      if (customerAuth) {
        try {
          await bindSelectionCustomer(session.id, accessToken, customerAuth.token);
        } catch (error) {
          if (authFailureAction(error) === 'reauthenticate') {
            clearCustomerAuth();
            setCustomerAuth(null);
            openRecordLogin();
            return;
          }
          throw error;
        }
      }
      const quote = await quoteSelectionSession(session.id, accessToken, submissionItems, deviceLabel());
      if (quote.saving_hint?.kind === 'member') {
        setSavingHint(quote.saving_hint);
        setSavingHintOpen(true);
        openOverlay('saving-hint');
        return;
      }
      await submitRevision();
    } catch (error) {
      flash(error instanceof Error ? error.message : '报价失败，请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  const submitServiceFeedback = async (input: { rating: number; tags: string[]; note: string }) => {
    if (!session || !(feedbackToken || accessToken)) return;
    setFeedbackSubmitting(true);
    try {
      await submitFeedback(session.id, feedbackToken || accessToken, input);
      setServiceStatus((current) => current ? { ...current, can_evaluate: true, evaluated: true } : current);
      flash('评价已提交');
    } catch (error) {
      flash(error instanceof Error ? error.message : '评价暂未提交，请稍后重试');
    } finally {
      setFeedbackSubmitting(false);
    }
  };

  if (boot === 'loading') {
    return <main className="loading-screen"><span className="loading-mark">荷</span><div className="loading-line" /><p>{bootMessage}</p></main>;
  }
  if (boot === 'pick-position') {
    return <InitialPositionPicker positions={positions} onSelect={selectInitialPosition} onBlocked={setBootMessage} busy={false} message={bootMessage === '正在连接门店服务' ? '' : bootMessage} />;
  }
  if (boot === 'occupied') {
    return <StatusScreen type="occupied" title="这个位置已经有人" message={bootMessage || '请核对您所在的沙发，或联系前台协助处理。'} onRetry={retry} />;
  }
  if (boot === 'expired') {
    const copy = expiredSelectionCopy();
    return <StatusScreen type="expired" title={copy.title} message={copy.message} onRetry={retry} />;
  }
  if (boot === 'kiosk-unbound') {
    return <StatusScreen type="error" title={KIOSK_UNBOUND_COPY.title} message={KIOSK_UNBOUND_COPY.message} />;
  }
  if (boot === 'error') {
    return <StatusScreen type="error" title="暂时没有连接上" message={bootMessage} onRetry={retry} />;
  }
  if (boot === 'submitted' && session) {
    const feedbackAction = serviceFeedbackAction(Boolean(serviceStatus?.can_evaluate), Boolean(serviceStatus?.evaluated));
    return (
      <main className="success-screen" onTouchStart={handleTouchStart} onTouchEnd={handleTouchEnd} onTouchCancel={handleTouchCancel}>
        <div className="success-top">
          <span className="success-symbol"><CheckCircle2 size={36} /></span>
          <span className="eyebrow">{serviceProgress.eyebrow}</span>
          <h1>{serviceProgress.title}</h1>
          <p>{position?.customer_label || '服务位置'} · {serviceProgress.message}</p>
        </div>
        <section className="success-order" id="success-order">
          <header><strong>本次选择</strong><span>{session.items.filter((item) => item.item_type === 'service').length} 项服务 · 共 {totalServiceMinutes} 分钟</span></header>
          {session.items.map((item, index) => {
            const serviceIndex = session.items.slice(0, index + 1).filter((candidate) => candidate.item_type === 'service').length - 1;
            const line = item.item_type === 'service' && Array.isArray(session.pricing_snapshot?.lines) ? (session.pricing_snapshot.lines as Array<Record<string, unknown>>)[serviceIndex] : null;
            const duration = serviceDurationMinutes(item);
            return (
            <div className="success-line" key={`${item.project_id}-${index}`}>
              <div><strong>{item.name || (item.project_id === 'tea' ? '到店茶饮' : '服务项目')}</strong><small>{item.diy_preferences?.join(' · ') || '按门店标准服务'}</small>{item.item_type === 'service' && <small className="success-line-meta">{line && Number.isFinite(Number(line.unit_payable_price_cents)) ? `单价 ${formatMoney(Number(line.unit_payable_price_cents))}` : ''}{duration > 0 ? `${line && Number.isFinite(Number(line.unit_payable_price_cents)) ? ' · ' : ''}服务约 ${duration} 分钟` : ''}</small>}</div>
              {item.item_type === 'preference' ? <span>赠饮</span> : <Check size={16} />}
            </div>
            );
          })}
          {Number(session.pricing_snapshot?.promotion_adjustment_cents || 0) < 0 && (
            <div className="success-promo"><Sparkles size={17} />已减免草本泡脚费 {formatMoney(Math.abs(Number(session.pricing_snapshot?.promotion_adjustment_cents)))}</div>
          )}
          <footer>
            <span>{priceDisplay.primaryLabel}{priceDisplay.originalHint && <small className="success-member-hint">{priceDisplay.originalHint}</small>}{priceDisplay.realizedSavingCents > 0 && <small className="success-saving">已省 {formatMoney(priceDisplay.realizedSavingCents)}</small>}{priceDisplay.memberHint && <small className="success-member-hint">办理年度权益卡后可享 {priceDisplay.memberHint}</small>}{priceDisplay.savingCents > 0 && <small className="success-saving">预计可省 {formatMoney(priceDisplay.savingCents)}</small>}</span>
            <strong>{formatMoney(payableTotal)}</strong>
          </footer>
        </section>
        <div className="success-note">服务完成后统一线下结算，最终以门店确认的服务清单为准。</div>
        <div className="success-actions">
          <button className="primary-action" type="button" onClick={returnToProjectListAfterSubmit}><ListChecks size={18} />返回项目列表</button>
          {feedbackAction && <button className="secondary-action" type="button" disabled={Boolean(serviceStatus?.evaluated)} onClick={openFeedback}><MessageSquareText size={17} />{feedbackAction}</button>}
          {shouldOfferRecordBinding(Boolean(serviceStatus?.evaluated), customerAuth) && (
            <button className="secondary-action" type="button" onClick={openRecordLogin}>手机号保存本次记录</button>
          )}
        </div>
        <FeedbackDialog
          open={feedbackOpen}
          submitting={feedbackSubmitting}
          submitted={Boolean(serviceStatus?.evaluated)}
          onClose={dismissTopOverlay}
          onSubmit={submitServiceFeedback}
        />
        <RecordLoginDialog
          open={recordLoginOpen}
          selectionSessionId={session.id}
          selectionToken={feedbackToken || accessToken}
          onClose={dismissTopOverlay}
          onSuccess={(auth) => {
            refreshAfterCustomerLogin(auth, '已识别身份，价格已更新');
            dismissTopOverlay();
          }}
        />
      </main>
    );
  }

  return (
    <div className="customer-app" onTouchStart={handleTouchStart} onTouchEnd={handleTouchEnd} onTouchCancel={handleTouchCancel}>
      {!online && <div className="offline-banner"><WifiOff size={15} />网络已断开，恢复后将继续同步</div>}
      <header className="miniapp-context-bar">
        <div className="miniapp-store" onClick={openSeatMap} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openSeatMap(); } }} role="button" tabIndex={0}>
          <MapPinned size={16} />
          <span>荷小悦草本泡脚</span>
          <em>{position?.customer_label || '服务位待核对'}</em>
          <small>切换</small>
        </div>
        <button className="miniapp-profile-entry" type="button" onClick={openProfile}>
          <CircleUserRound size={18} />
          <span>{customerAuth ? '我的' : '登录'}</span>
        </button>
      </header>

      {boot === 'ready' && hasSubmittedCustomerSession && <div className="submitted-browse-banner"><span><CheckCircle2 size={16} />{serviceProgress.browseLabel}</span><button type="button" onClick={() => setBoot('submitted')}>查看清单</button></div>}

      <section className="miniapp-promo-strip" aria-label="门店推荐">
        {shouldShowMembershipPromos(isMember) && <>
        <button type="button" className="miniapp-promo membership-promo annual" onClick={() => openMembership('annual')}>
          <span className="promo-copy"><small>年度权益 · 全年会员价</small><strong>99元会员年度权益卡</strong><em>到店办理<i>开通后生效</i></em></span>
          <span className="membership-promo-badge">99</span>
        </button>
        <button type="button" className="miniapp-promo membership-promo monthly" onClick={() => openMembership('monthly')}>
          <span className="promo-copy"><small>不限次泡脚</small><strong>泡脚月卡 30 天</strong><em>到店办理<i>仅限本人</i></em></span>
          <span className="membership-promo-badge">499</span>
        </button>
        </>}
        {featured.map((project, index) => (
          <button key={project.id} type="button" className={`miniapp-promo ${index === 0 ? 'primary' : ''}`} onClick={() => openProjectDetail(project)}>
            <span className="promo-copy"><small>{pageContent?.promo_banners[index]?.eyebrow || (index === 0 ? '新客体验' : index === 1 ? '门店推荐' : index === 2 ? '慢享时光' : '调理套盒')}</small><strong>{pageContent?.promo_banners[index]?.title || displayProjectName(project)}</strong><em>{formatMoney(priceGuidance(project, customerAuth?.user || null).primaryCents)}<i>起</i></em></span>
            <img src={projectImage(project)} alt="" loading="lazy" decoding="async" />
          </button>
        ))}
      </section>

      <div className="catalog-layout miniapp-catalog-layout">
        <nav className="category-nav" aria-label="项目分类">
          {CATALOG_SECTIONS.map((section) => (
            <button
              key={section.id}
              type="button"
              data-category-id={section.id}
              aria-current={activeSection === section.id ? 'true' : undefined}
              className={activeSection === section.id ? 'active' : ''}
              onClick={() => {
                setActiveSection(section.id);
                sectionScrollTargetRef.current = section.id;
                const catalogMain = catalogMainRef.current;
                const target = document.getElementById(`section-${section.id}`);
                if (catalogMain && target) {
                  catalogMain.scrollTo({ top: target.offsetTop, behavior: 'smooth' });
                }
              }}
            >
              <strong>{section.mark}</strong><small>{section.label}</small>
            </button>
          ))}
        </nav>

        <main className="catalog-main" ref={(element) => { catalogMainRef.current = element; }}>
          <section className="catalog-section tea-section" id="section-tea">
            <div className="section-heading"><div><span className="eyebrow">{pageContent?.title || '到店赠饮'}</span><h2>茶｜茶饮</h2></div><span>{customerPageSubtitle(pageContent?.subtitle)}</span></div>
            <article className={`project-card mini-project-row preference-project-row ${tea ? 'selected' : ''}`} onClick={openTeaDetail} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openTeaDetail(); } }} role="button" tabIndex={0}>
              <div className="project-photo"><img src={TEA_SERVICE.image} alt="" loading="lazy" decoding="async" /></div>
              <div className="project-copy">
                <div className="project-title-row"><h3>{TEA_SERVICE.name}</h3></div>
                <p>{TEA_SERVICE.summary}</p>
                <div className="project-badges"><span>到店奉茶</span><span>随项目</span></div>
                <div className="preference-project-foot"><strong>{tea ? `已选：${tea}` : '免费到店茶饮 · 可选配方'}</strong></div>
              </div>
              <button className={`detail-arrow luckin-add ${tea ? 'selected' : ''}`} type="button" aria-label="选择茶饮" aria-pressed={Boolean(tea)} onClick={(event) => { event.stopPropagation(); openTeaDetail(); }}><Plus size={18} /></button>
            </article>
          </section>

          {CATALOG_SECTIONS.filter((section) => section.id !== 'tea').map((section) => {
            const sectionProjects = projects.filter((project) => section.categories.includes(project.category as never) && project.category !== 'local-strength');
            if (!sectionProjects.length) return null;
            return (
              <section className="catalog-section" id={`section-${section.id}`} key={section.id}>
                <div className="section-heading"><div><span className="eyebrow">{section.mark}</span><h2>{section.label}</h2></div><span>{sectionProjects.length} 项</span></div>
                <div className="project-grid">
                  {sectionProjects.map((project) => {
                    const selected = selectedProjectIds.includes(project.id);
                    const displayName = displayProjectName(project);
                    const { highlights, summary: summaryTags, purchase: purchaseTags } = customerProjectDisplayTagGroups(project);
                    return (
                      <motion.article whileTap={{ scale: 0.985 }} className={`project-card mini-project-row ${selected ? 'selected' : ''}`} key={project.id} onClick={() => openProjectDetail(project)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openProjectDetail(project); } }} role="button" tabIndex={0}>
                        <div className="project-photo"><img src={projectImage(project)} alt="" loading="lazy" decoding="async" />{project.code === 'hxy-xiaoqi-90' && <span className="signature-badge">招牌</span>}</div>
                        <div className="project-copy">
                          <div className="project-title-row"><h3>{displayName}</h3>{project.duration_min && <span>{project.duration_min}分钟</span>}</div>
                          <p>{customerProjectSummaryText(project)}</p>
                          {(highlights.length > 0 || summaryTags.length > 0 || purchaseTags.length > 0) && <div className="project-badge-groups" aria-label="项目标签">
                            {highlights.length > 0 && <div className="project-badges project-badges-highlight" aria-label="项目特色">{highlights.map((tag) => <span key={tag}>{tag}</span>)}</div>}
                            {summaryTags.length > 0 && <div className="project-badges project-badges-summary" aria-label="项目简介">{summaryTags.map((tag) => <span key={tag}>{tag}</span>)}</div>}
                            {purchaseTags.length > 0 && <div className="project-badges project-badges-purchase" aria-label="选购规则">{purchaseTags.map((tag) => <span key={tag}>{tag}</span>)}</div>}
                          </div>}
                          <ProjectPrice project={project} auth={customerAuth?.user || null} />
                          {projectPreferences[project.id]?.length > 0 && <div className="preference-line">{projectPreferences[project.id].join(' · ')}</div>}
                        </div>
                        <button className={`detail-arrow luckin-add ${selected ? 'selected' : ''}`} type="button" aria-label={selected ? `调整${displayName}` : `选择${displayName}`} aria-pressed={selected} onClick={(event) => { event.stopPropagation(); openProjectDetail(project); }}>
                          <Plus size={18} />
                        </button>
                      </motion.article>
                    );
                  })}
                </div>
                {section.id === 'small' && localProject && <article className={`project-card mini-project-row preference-project-row ${localParts.length ? 'selected' : ''}`} onClick={openLocalDetail} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openLocalDetail(); } }} role="button" tabIndex={0}>
                  <div className="project-photo"><img src={projectImage(localProject)} alt="" loading="lazy" decoding="async" /></div>
                  <div className="project-copy">
                    <div className="project-title-row"><h3>{displayProjectName(localProject)}</h3><span>{localProject.duration_min || 30}分钟/项</span></div>
                    <p>肩颈、腰臀、腿部、腹部、足部，按需灵活选择。</p>
                    {customerProjectPurchaseTags(localProject).length > 0 && <div className="project-badges project-badges-purchase" aria-label="选购规则">{customerProjectPurchaseTags(localProject).map((tag) => <span key={tag}>{tag}</span>)}</div>}
                    <ProjectPrice project={localProject} auth={customerAuth?.user || null} />
                    {localParts.length > 0 && <div className="preference-line">已选：{localParts.join(' · ')}</div>}
                  </div>
                  <button className={`detail-arrow luckin-add ${localParts.length ? 'selected' : ''}`} type="button" aria-label={`选择${displayProjectName(localProject)}`} aria-pressed={localParts.length > 0} onClick={(event) => { event.stopPropagation(); openLocalDetail(); }}><Plus size={18} /></button>
                </article>}
              </section>
            );
          })}

          <div className="catalog-end"><span>荷</span><p>选好后提交给前台，服务前由门店再次确认。</p></div>
        </main>
      </div>

      <AnimatePresence initial={false}>
      {selectedCount > 0 && <motion.footer data-motion="selection-footer" {...sheetMotion} className="selection-footer">
        <button className="selection-summary" type="button" aria-haspopup="dialog" aria-expanded={selectionSummaryOpen} onClick={openSelectionSummary}>
          <span className="selection-bag"><ShoppingBag size={27} /><span className="selection-count">{selectedCount}</span></span>
          <span className="selection-price-copy">
            <span className="selection-summary-total"><small>{saving ? '正在更新' : '预计合计'}</small><strong>{formatMoney(payableTotal)}</strong></span>
            <span className="selection-summary-meta">{isMember ? <>{priceDisplay.originalHint && <del>{priceDisplay.originalHint}</del>}{priceDisplay.realizedSavingCents > 0 && <b>已优惠 {formatMoney(priceDisplay.realizedSavingCents)}</b>}{!priceDisplay.realizedSavingCents && <span>已按会员价计算</span>}</> : priceDisplay.memberHint ? <><span className="selection-summary-member-price">{priceDisplay.memberHint}</span>{priceDisplay.savingCents > 0 && <b>可省 {formatMoney(priceDisplay.savingCents)}</b>}</> : <span>{priceDisplay.primaryLabel} · 查看清单</span>}</span>
          </span>
        </button>
        <button className="submit-button" type="button" disabled={readOnly || submitting || !online} onClick={submit}>
          {readOnly ? '已提交前台' : submitting ? '正在提交' : '提交给前台'}<ChevronRight size={18} />
        </button>
      </motion.footer>}
      </AnimatePresence>

      <AnimatePresence initial={false}>
      {selectionSummaryOpen && <SelectionSummarySheet
        open
        summary={selectionSummary}
        promotion={selectionPromotion}
        totalCents={payableTotal}
        priceLabel={priceDisplay.primaryLabel}
        memberHint={priceDisplay.memberHint}
        savingCents={priceDisplay.savingCents}
        originalHint={priceDisplay.originalHint}
        realizedSavingCents={priceDisplay.realizedSavingCents}
        saving={saving}
        readOnly={readOnly}
        positionLabel={position?.customer_label || '服务位置待确认'}
        identityLabel={customerAuth?.user.is_member ? '会员价' : customerAuth ? '普通顾客' : '匿名顾客'}
        onClose={dismissTopOverlay}
        onModify={handleSummaryModify}
        onRemove={handleSummaryRemove}
        onQuantityChange={handleSummaryQuantityChange}
      />}
      </AnimatePresence>

      <SeatMapDialog open={seatMapOpen} current={position} positions={positions} moving={moving} source={session?.source || occupancy?.source || query.source} onClose={dismissTopOverlay} onSelect={handleMove} onBlocked={flash} />
      <AnimatePresence initial={false} mode="wait">
      {teaDetailOpen && <TeaDetailPage open selectedTea={tea} teaOptions={pageContent?.tea_options} positionLabel={position?.customer_label || '服务位待核对'} readOnly={readOnly} onClose={dismissTopOverlay} onConfirm={selectTea} />}
      {localDetailOpen && <LocalDetailPage open project={localProject || null} selectedParts={localParts} positionLabel={position?.customer_label || '服务位待核对'} isMember={isMember} readOnly={readOnly} onClose={dismissTopOverlay} onConfirm={saveLocalParts} />}
      {detailProject && <ProjectDetailPage
        project={detailProject}
        projects={projects}
        addons={addons}
        selectedProjectIds={selectedProjectIds}
        selectedAddonIds={detailProject ? projectAddonIds[detailProject.id] || [] : []}
        preferences={detailProject ? projectPreferences[detailProject.id] || [] : []}
        localParts={localParts}
        catalogSelection={detailProject ? projectCatalogSelections?.[detailProject.id] : undefined}
        coupon={featuredCoupon}
        positionLabel={position?.customer_label || '服务位待核对'}
        isMember={isMember}
        readOnly={readOnly}
        onClose={dismissTopOverlay}
        onConfirm={saveProject}
        onCouponInfo={openCouponLogin}
        couponPrompt={pageContent?.coupon_prompt}
      />}
      </AnimatePresence>
      <CouponLoginDialog
        open={couponLoginOpen}
        coupon={featuredCoupon}
        auth={customerAuth}
        selectionSessionId={session?.id}
        selectionToken={accessToken}
        onClose={dismissTopOverlay}
        onSuccess={handleCouponSuccess}
      />
      <SavingHintDialog
        hint={savingHint}
        open={savingHintOpen}
        onLogin={() => {
          pageTracking.loginPromptView({ prompt_type: 'record', trigger: 'saving_hint' });
          setSavingHintOpen(false);
          setRecordLoginOpen(true);
          replaceTopOverlay('record-login');
        }}
        onSkip={() => {
          dismissTopOverlay();
          void submitRevision();
        }}
      />
      <RecordLoginDialog
        open={recordLoginOpen}
        selectionSessionId={session?.id || ''}
        selectionToken={accessToken || ''}
        onClose={dismissTopOverlay}
        onSuccess={(auth) => {
          refreshAfterCustomerLogin(auth, '已识别身份，价格已更新');
          dismissTopOverlay();
        }}
      />
      <ProfilePage
        open={profileOpen}
        auth={customerAuth}
        onClose={dismissTopOverlay}
        onAuthChange={(auth) => {
          if (auth) refreshAfterCustomerLogin(auth, '登录成功');
          else {
            clearCustomerAuth();
            setCustomerAuth(null);
          }
        }}
      />
      <MembershipDetailPage kind={membershipKind} open={Boolean(membershipKind)} onClose={dismissTopOverlay} />
      <AnimatePresence>
        {toast && (
          <motion.div className="toast" role="status" {...toastMotion}>
            <CheckCircle2 size={17} />{toast}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

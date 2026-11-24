import { ArrowLeft, BadgeCheck, Bookmark, CalendarDays, ChevronRight, Clock3, LogOut, MessageSquareText, ReceiptText, Store, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { QRCodeSVG } from 'qrcode.react';

import { ApiError, cancelOrder, enrollTrustedDevice, getCouponRedeemToken, getMyCoupons, getMySelectionSessions, issueMemberCode, loginByPhone, rebindTrustedDevice, sendPhoneCode, submitCustomerFeedback, type MyCoupon, type Order, type SelectionSession } from '../api';
import { authFailureAction, clearCustomerAuth, isValidPhone, normalizePhone, writeCustomerAuth, type CustomerAuth } from '../customerAuth';
import { assetPath, formatMoney } from '../domain';
import { useCustomerMembership } from './useCustomerMembership';
import { useCustomerConsumption } from './useCustomerConsumption';
import { customerLoginCopy, shouldShowCouponTab } from '../customerCopy';
import { bindPendingGuestCoupons } from '../guestCoupon';
import { canSelfCancelOrder, couponStatusLabel, formatDateTime, orderStatusLabel, recordFilter, selectionDisplayAmount, selectionStatusLabel, type RecordFilter } from '../profile';
import MembershipBanner from './MembershipBanner';
import FeedbackDialog from './FeedbackDialog';
import MyReports from './MyReports';
import { ProfileReturnTools, ReturnDialog } from './CustomerReturnTools';
import './profile-home.css';
import ProfileMemberOverview from './ProfileMemberOverview';

type TabKey = 'records' | 'coupons';

// Temporary customer presentation switches; server rules and records remain intact.
const SHOW_PROFILE_HISTORY = true;
const SHOW_DYNAMIC_MEMBER_CODE = false;
const OPEN_COUPON_ON_MOUNT = typeof window !== 'undefined'
  && new URLSearchParams(window.location.search).get('coupon') === '1';

export default function ProfilePage({ open, auth, onClose, onAuthChange, initialReportsOpen = false, onReportsBack, onOpenReports, storeId = 1, refreshKey = 0, navigation }: {
  open: boolean;
  auth: CustomerAuth | null;
  onClose: () => void;
  onAuthChange: (auth: CustomerAuth | null) => void;
  initialReportsOpen?: boolean;
  onReportsBack?: () => void;
  onOpenReports?: () => void;
  storeId?: number;
  refreshKey?: number;
  navigation?: ReactNode;
}) {
  const [tab, setTab] = useState<TabKey>(OPEN_COUPON_ON_MOUNT ? 'coupons' : 'records');
  const [reportsOpen, setReportsOpen] = useState(initialReportsOpen);
  const openReports = () => onOpenReports ? onOpenReports() : setReportsOpen(true);
  const [recordState, setRecordState] = useState<RecordFilter>('all');
  const [selectedRecord, setSelectedRecord] = useState<SelectionSession | null>(null);
  const [feedbackRecord, setFeedbackRecord] = useState<SelectionSession | null>(null);
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const [feedbackError, setFeedbackError] = useState('');
  const feedbackRequest = useRef<object | null>(null);
  const [dataOwner, setDataOwner] = useState<string | null>(null);
  const [returnPanel, setReturnPanel] = useState<'save' | 'contact' | 'tuesday' | null>(null);
  const [recordsOpen, setRecordsOpen] = useState(OPEN_COUPON_ON_MOUNT);
  const recordTrigger = useRef<HTMLButtonElement | null>(null);
  const [recordLimit, setRecordLimit] = useState(3);
  const [recordNavigation, setRecordNavigation] = useState(0);
  const recordSection = useRef<HTMLElement>(null);
  const [memberCodeOpen, setMemberCodeOpen] = useState(false);
  const membership = useCustomerMembership(open, auth?.token || null, () => { clearCustomerAuth(); onAuthChange(null); }, undefined, refreshKey);
  const consumption = useCustomerConsumption(open, auth?.token || null, () => { clearCustomerAuth(); onAuthChange(null); }, undefined, refreshKey);
  const [orders, setOrders] = useState<Order[]>([]);
  const [sessions, setSessions] = useState<Awaited<ReturnType<typeof getMySelectionSessions>>>([]);
  const [coupons, setCoupons] = useState<MyCoupon[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [cancelling, setCancelling] = useState(false);
  const loadRequest = useRef(0);
  const loadContext = useRef({ open, auth, reportsOpen, onAuthChange });
  loadContext.current = { open, auth, reportsOpen, onAuthChange };

  useEffect(() => { if (open && initialReportsOpen) setReportsOpen(true); }, [open, initialReportsOpen]);
  useEffect(() => {
    if (!open) return;
    if (OPEN_COUPON_ON_MOUNT) setTab('coupons');
  }, [open]);

  const loadData = useCallback((token: string, isMember: boolean) => {
    const requestId = ++loadRequest.current;
    const isCurrent = () => requestId === loadRequest.current && loadContext.current.open && !loadContext.current.reportsOpen
      && loadContext.current.auth?.token === token && loadContext.current.auth.user.is_member === isMember;
    setLoading(true);
    setLoadError('');
    Promise.all([
      Promise.resolve([] as Order[]),
      SHOW_PROFILE_HISTORY ? getMySelectionSessions(token) : Promise.resolve([] as SelectionSession[]),
      // 会员不展示券入口，也不应请求会员无权限的券接口；否则任一 403 会让整个个人中心误报加载失败。
      getMyCoupons(token),
    ]).then(([orderItems, sessionItems, couponItems]) => {
      if (!isCurrent()) return;
      setDataOwner(token);
      setOrders(orderItems);
      setSessions(sessionItems);
      setCoupons(couponItems);
    }).catch((reason) => {
      if (!isCurrent()) return;
      if (['reauthenticate', 'session-replaced'].includes(authFailureAction(reason))) {
        clearCustomerAuth();
        loadContext.current.onAuthChange(null);
        return;
      }
      setLoadError(reason instanceof TypeError ? '网络暂时不稳定，请检查网络后重试。' : reason instanceof Error ? reason.message : '服务记录加载失败，请稍后重试');
    }).finally(() => { if (isCurrent()) setLoading(false); });
  }, []);

  useEffect(() => {
    if (!open || !auth || reportsOpen) { setLoading(false); return; }
    loadData(auth.token, auth.user.is_member);
    return () => { loadRequest.current += 1; };
  }, [open, auth?.token, auth?.user.is_member, reportsOpen, loadData, refreshKey]);

  useEffect(() => { setSelectedRecord(null); setFeedbackRecord(null); setFeedbackError('');
    setFeedbackSubmitting(false); feedbackRequest.current = null;
    setMemberCodeOpen(false); setReturnPanel(null); setRecordsOpen(OPEN_COUPON_ON_MOUNT); setRecordState('all');
    setRecordLimit(3); setRecordNavigation(0);
    setTab(OPEN_COUPON_ON_MOUNT ? 'coupons' : 'records');
  }, [auth?.token]);

  useEffect(() => {
    if (!recordNavigation) return;
    recordSection.current?.scrollIntoView({ block: 'start', behavior: 'auto' });
    recordSection.current?.focus({ preventScroll: true });
  }, [recordNavigation]);

  const ownsData = Boolean(auth && dataOwner === auth.token);
  const visibleSessions = ownsData ? sessions : [];
  const visibleCoupons = ownsData ? coupons : [];
  const filteredSessions = recordFilter(visibleSessions, recordState);
  const pendingCount = visibleSessions.filter(item => item.can_evaluate && !item.evaluated).length;
  const showRecords = (filter: RecordFilter = 'all', trigger?: HTMLButtonElement) => {
    recordTrigger.current = trigger || null; setRecordsOpen(true);
    setTab('records'); setRecordState(filter); setRecordLimit(3);
    setRecordNavigation(value => value + 1);
  };
  const openFeedback = (record: SelectionSession) => {
    setFeedbackError(''); setFeedbackRecord(record);
  };
  const saveFeedback = async (input: { rating: number; tags: string[]; note: string }) => {
    if (!auth || !ownsData || !feedbackRecord || feedbackRequest.current) return;
    const request = {}; const token = auth.token; const recordId = feedbackRecord.id;
    feedbackRequest.current = request; setFeedbackSubmitting(true); setFeedbackError('');
    const isCurrent = () => loadContext.current.open && loadContext.current.auth?.token === token && feedbackRequest.current === request;
    try {
      await submitCustomerFeedback(recordId, token, input);
      if (!isCurrent()) return;
      setFeedbackRecord({ ...feedbackRecord, evaluated: true });
      setSessions(items => items.map(item => item.id === recordId ? { ...item, evaluated: true } : item));
      loadData(token, auth.user.is_member);
    } catch (reason) {
      if (!isCurrent()) return;
      if (['reauthenticate', 'session-replaced'].includes(authFailureAction(reason))) {
        clearCustomerAuth(); loadContext.current.onAuthChange(null); return;
      }
      setFeedbackError(reason instanceof TypeError ? '网络暂时不稳定，请重试。已保留填写内容。' : reason instanceof Error ? reason.message : '评价未提交成功，请重试');
    } finally {
      if (feedbackRequest.current === request) {
        feedbackRequest.current = null; setFeedbackSubmitting(false);
      }
    }
  };

  const handleCancelOrder = async (order: Order) => {
    if (!auth || cancelling) return;
    if (!window.confirm(`确认取消服务单 ${order.order_no}？取消后不可恢复。`)) return;
    setCancelling(true);
    try {
      await cancelOrder(order.id, auth.token);
      loadData(auth.token, auth.user.is_member);
    } catch (reason) {
      if (['reauthenticate', 'session-replaced'].includes(authFailureAction(reason))) {
        clearCustomerAuth();
        onAuthChange(null);
        return;
      }
      setLoadError(reason instanceof Error ? reason.message : '取消失败，请稍后重试');
    } finally {
      setCancelling(false);
    }
  };

  if (!open) return null;

  return (
    <div className={`profile-page ${reportsOpen ? 'profile-report-view' : 'profile-home'}${auth ? '' : ' profile-guest'}`} role="dialog" aria-modal="true" aria-label="个人中心">
      <header>
        <button type="button" aria-label={reportsOpen ? onReportsBack ? '返回首页' : '返回我的' : '返回'} onClick={reportsOpen ? onReportsBack || (() => setReportsOpen(false)) : onClose}><ArrowLeft size={22} /></button>
        <strong>{reportsOpen ? '我的检测报告' : '我的'}</strong>
        {auth ? <button className="profile-logout" type="button" onClick={() => { clearCustomerAuth(); onAuthChange(null); }}><LogOut size={15} />退出登录</button> : <span />}
      </header>

      {!auth
        ? <main className="profile-anonymous-body">
            <div className="profile-guest-content">
              <ProfileLogin onAuthChange={onAuthChange} forReports={reportsOpen} />
              {!reportsOpen && <ProfileReturnTools onReports={openReports} onPanel={setReturnPanel} />}
            </div>
          </main>
        : reportsOpen ? <MyReports key={auth.token} token={auth.token} onVerify={() => { clearCustomerAuth(); onAuthChange(null); }} /> : (
          <main className="profile-body">
            <ProfileMemberOverview key={auth.token} user={auth.user} membership={membership} consumption={consumption} showMemberCode={SHOW_DYNAMIC_MEMBER_CODE} onShowCode={() => setMemberCodeOpen(true)} />
            <h2 className="profile-overview-services-title">常用服务</h2>
            <nav className="profile-shortcuts" aria-label="常用功能">
              <button type="button" aria-expanded={recordsOpen && recordState !== 'pending-feedback'} aria-controls="profile-records" onClick={event => showRecords('all', event.currentTarget)}><Clock3 size={23} aria-hidden="true" /><span>服务记录</span></button>
              <button type="button" aria-label={`待评价，${pendingCount}条`} aria-expanded={recordsOpen && recordState === 'pending-feedback'} aria-controls="profile-records" onClick={event => showRecords('pending-feedback', event.currentTarget)}><span className="profile-shortcut-icon"><MessageSquareText size={23} aria-hidden="true" />{pendingCount > 0 && <em aria-hidden="true">{pendingCount}</em>}</span><span>待评价</span></button>
              <button type="button" onClick={openReports}><ReceiptText size={23} aria-hidden="true" /><span>检测报告</span></button>
              <button type="button" onClick={() => setReturnPanel('save')}><Bookmark size={23} aria-hidden="true" /><span>服务号</span></button>
              <button type="button" onClick={() => setReturnPanel('contact')}><Store size={23} aria-hidden="true" /><span>联系门店</span></button>
              <button type="button" onClick={() => setReturnPanel('tuesday')}><CalendarDays size={23} aria-hidden="true" /><span>超级星期二</span></button>
            </nav>
            {!recordsOpen && loadError && <div className="profile-load-error" role="alert"><p>{loadError}</p><button type="button" onClick={() => loadData(auth.token, auth.user.is_member)}>重新加载</button></div>}
            {recordsOpen && <section id="profile-records" className="profile-records-section" ref={recordSection} tabIndex={-1} aria-label="我的服务记录">
              <div className="profile-section-heading"><h2>{tab === 'records' ? '服务记录' : '券包'}</h2>{tab === 'records' && <span>{visibleSessions.length >= 50 ? '最近50条' : '最近到店'}</span>}{shouldShowCouponTab(auth.user.is_member) && <button type="button" onClick={() => { setTab(tab === 'records' ? 'coupons' : 'records'); }}>{tab === 'records' ? '券包' : '服务记录'}<ChevronRight size={14} /></button>}<button className="profile-collapse-records" type="button" onClick={() => { setRecordsOpen(false); recordTrigger.current?.focus(); }}>收起<X size={14} /></button></div>
              {SHOW_PROFILE_HISTORY && tab === 'records' && <RecordFilters value={recordState} onChange={value => { setRecordState(value); setRecordLimit(3); }} />}
              {loadError && <div className="profile-load-error" role="alert"><p>{loadError}</p><button type="button" onClick={() => loadData(auth.token, auth.user.is_member)}>重新加载</button></div>}
              {loading && <p className="profile-empty" role="status">正在加载服务记录…</p>}
              {!loading && !loadError && (
                SHOW_PROFILE_HISTORY && tab === 'records' ? <>
                  <SelectionList sessions={filteredSessions.slice(0, recordLimit)} filter={recordState} onContinue={onClose} onOpen={setSelectedRecord} onFeedback={openFeedback} />
                  {filteredSessions.length > recordLimit && <button className="profile-more-records" type="button" onClick={() => setRecordLimit(value => value + 5)}>查看更多记录<ChevronRight size={15} /></button>}
                </> : shouldShowCouponTab(auth.user.is_member) ? <CouponList coupons={visibleCoupons} token={auth.token} /> : SHOW_PROFILE_HISTORY ? <OrderList orders={ownsData ? orders : []} cancelling={cancelling} onCancel={handleCancelOrder} /> : null
              )}
            </section>}
            {!auth.user.is_member && <MembershipBanner />}
            {ownsData && selectedRecord && <RecordDetail record={selectedRecord} onClose={() => setSelectedRecord(null)} onFeedback={() => { openFeedback(selectedRecord); setSelectedRecord(null); }} />}
            <FeedbackDialog key={auth.token} open={ownsData && Boolean(feedbackRecord)} submitting={feedbackSubmitting} submitted={Boolean(feedbackRecord?.evaluated)} error={feedbackError} onClose={() => { setFeedbackRecord(null); setFeedbackError(''); }} onSubmit={saveFeedback} />
            {SHOW_DYNAMIC_MEMBER_CODE && memberCodeOpen && <MemberCodeDialog token={auth.token} phone={auth.user.phone} onTokenReplaced={(token) => { const next = { ...auth, token }; writeCustomerAuth(next); onAuthChange(next); }} onClose={() => setMemberCodeOpen(false)} />}
          </main>
        )}
      <ReturnDialog panel={returnPanel} storeId={storeId} onClose={() => setReturnPanel(null)} />
      {!reportsOpen && !selectedRecord && !feedbackRecord && !returnPanel && !memberCodeOpen && navigation}
    </div>
  );
}

function ProfileLogin({ onAuthChange, forReports }: { onAuthChange: (auth: CustomerAuth) => void; forReports: boolean }) {
  const copy = customerLoginCopy('profile');
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [sentTo, setSentTo] = useState('');
  const [seconds, setSeconds] = useState(0);
  const [pending, setPending] = useState<'send' | 'login' | null>(null);
  const [error, setError] = useState<{ field: 'phone' | 'code' | 'form'; text: string } | null>(null);
  const phoneField = useRef<HTMLInputElement>(null);
  const codeField = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (seconds <= 0) return undefined;
    const timer = window.setTimeout(() => setSeconds(value => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [seconds]);

  const checkPhone = () => {
    if (isValidPhone(phone)) return true;
    setError({ field: 'phone', text: '请输入正确的 11 位手机号' });
    phoneField.current?.focus();
    return false;
  };

  const send = async () => {
    if (pending || seconds > 0 || !checkPhone()) return;
    setPending('send');
    setError(null);
    setSentTo('');
    try {
      await sendPhoneCode(phone);
      setSeconds(60);
      setSentTo(phone);
      codeField.current?.focus();
    } catch (reason) {
      setError({ field: 'form', text: reason instanceof Error ? reason.message : '验证码发送失败，请重试' });
    } finally {
      setPending(null);
    }
  };

  const confirm = async () => {
    if (pending || !checkPhone()) return;
    if (code.length !== 6) {
      setError({ field: 'code', text: '请输入短信中的 6 位验证码' });
      codeField.current?.focus();
      return;
    }
    setPending('login');
    setError(null);
    try {
      const result = await loginByPhone(phone, code);
      writeCustomerAuth(result);
      await bindPendingGuestCoupons(result.token);
      onAuthChange(result);
    } catch (reason) {
      setError({ field: 'form', text: reason instanceof Error ? reason.message : '登录失败，请重试' });
    } finally {
      setPending(null);
    }
  };

  return (
    <form className="profile-login" aria-labelledby="profile-login-title" noValidate
      onSubmit={event => { event.preventDefault(); void confirm(); }}>
      <div className="profile-login-heading">
        <div><h1 id="profile-login-title">{forReports ? '验证手机号' : copy.title}</h1>
          <p>{forReports ? '用检测时登记的手机号，查看本人报告。' : copy.detail}</p></div>
        <img src={assetPath('hxy-mascot.webp')} width="78" height="78" alt="" />
      </div>
      <div className="profile-login-fields">
        <div className="profile-login-field">
          <label htmlFor="profile-login-phone">手机号</label>
          <div className="profile-input-line">
            <input id="profile-login-phone" name="phone" ref={phoneField} type="tel" inputMode="tel" autoComplete="tel-national"
              placeholder={forReports ? '检测时登记的手机号' : '请输入到店使用的手机号'} readOnly={Boolean(pending)} value={phone}
              aria-invalid={error?.field === 'phone' || undefined} aria-describedby={error?.field === 'phone' ? 'profile-login-error' : undefined}
              onChange={event => { setPhone(normalizePhone(event.target.value)); setCode(''); setError(null); }} />
          </div>
        </div>
        <div className="profile-login-field">
          <label htmlFor="profile-login-code">短信验证码</label>
          <div className="profile-input-line">
            <input id="profile-login-code" name="code" ref={codeField} type="text" inputMode="numeric" autoComplete="one-time-code"
              enterKeyHint="go" placeholder="6 位验证码" maxLength={6} readOnly={pending === 'login'} value={code}
              aria-invalid={error?.field === 'code' || undefined} aria-describedby={error?.field === 'code' ? 'profile-login-error' : undefined}
              onChange={event => { setCode(event.target.value.replace(/\D/g, '').slice(0, 6)); setError(null); }} />
            <button className="profile-send-code" type="button" disabled={Boolean(pending) || seconds > 0} onClick={send}>
              {pending === 'send' ? '发送中…' : seconds > 0 ? `${seconds} 秒后重发` : '获取验证码'}
            </button>
          </div>
        </div>
      </div>
      {error ? <p className="profile-login-error" id="profile-login-error" role="alert">{error.text}</p>
        : sentTo && phone === sentTo && seconds > 0 && <p className="profile-login-sent" role="status">验证码已发送，请查看短信。</p>}
      <button className="profile-login-submit" type="submit" disabled={Boolean(pending)}>
        {pending === 'login' ? '正在登录…' : forReports ? '登录并查看报告' : copy.action}
      </button>
      <p className="profile-login-registration">首次登录会自动注册。</p>
    </form>
  );
}

function OrderList({ orders, cancelling, onCancel }: {
  orders: Order[]; cancelling: boolean; onCancel: (order: Order) => void;
}) {
  if (!orders.length) return <p className="profile-empty">还没有服务记录。完成一次到店服务后会在这里看到。</p>;
  return (
    <ul className="profile-list">
      {orders.map((order) => (
        <li key={order.id} className="profile-order">
          <div className="profile-list-head">
            <strong>{order.order_type === 'member' ? '会员权益' : '到店服务'}</strong>
            <span className={`profile-status status-${order.status}`}>{orderStatusLabel(order.status)}</span>
          </div>
          <p className="profile-order-no">{order.order_no} · {formatDateTime(order.created_at)}</p>
          {order.items.length > 0 && <p className="profile-order-items">{order.items.map((item) => `${item.name}×${item.quantity}`).join(' · ')}</p>}
          <div className="profile-list-foot">
            <span>{formatMoney(order.pay_amount_cents || order.total_amount_cents)}</span>
            {order.discount_cents > 0 && <del>{formatMoney(order.total_amount_cents)}</del>}
            {canSelfCancelOrder(order.status) && (
              <button className="profile-cancel-button" type="button" disabled={cancelling} onClick={() => onCancel(order)}>
                {cancelling ? '正在取消' : '取消服务单'}
              </button>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

function RecordFilters({ value, onChange }: { value: RecordFilter; onChange: (value: RecordFilter) => void }) {
  return <div className="profile-record-filters" aria-label="服务记录筛选">{([['all', '全部'], ['pending-feedback', '待评价'], ['in-service', '服务中'], ['completed', '已完成']] as const).map(([key, label]) => <button key={key} type="button" className={value === key ? 'active' : ''} aria-pressed={value === key} onClick={() => onChange(key)}>{label}</button>)}</div>;
}

function MemberCodeDialog({ token, phone, onTokenReplaced, onClose }: { token: string; phone: string; onTokenReplaced: (token: string) => void; onClose: () => void }) {
  const [code, setCode] = useState('');
  const [seconds, setSeconds] = useState(30);
  const [error, setError] = useState('');
  const [rebindCode, setRebindCode] = useState('');
  const [rebindMode, setRebindMode] = useState(false);
  const load = useCallback(async () => {
    setError('');
    try {
      let result;
      try { result = await issueMemberCode(token); }
      catch (reason) {
        if (reason instanceof ApiError && reason.code === 'DEVICE_NOT_TRUSTED') { await enrollTrustedDevice(token); result = await issueMemberCode(token); }
        else throw reason;
      }
      setCode(result.code_token); setSeconds(Math.max(1, Math.ceil((new Date(result.expires_at).getTime() - Date.now()) / 1000)));
    } catch (reason) { setCode(''); setRebindMode(reason instanceof ApiError && reason.code === 'DEVICE_ALREADY_BOUND'); setError(reason instanceof Error ? reason.message : '会员码生成失败'); }
  }, [token]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { if (!code) return; const timer = window.setInterval(() => setSeconds((value) => { if (value <= 1) { window.clearInterval(timer); void load(); return 0; } return value - 1; }), 1000); return () => window.clearInterval(timer); }, [code, load]);
  const enableHere = async () => { try { const result = await rebindTrustedDevice(token, rebindCode); onTokenReplaced(result.access_token); setRebindMode(false); } catch (reason) { setError(reason instanceof Error ? reason.message : '验证失败，请重试'); } };
  return <div className="profile-detail-backdrop" role="presentation" onClick={onClose}><section className="profile-member-code-dialog" role="dialog" aria-modal="true" aria-labelledby="member-code-title" onClick={(event) => event.stopPropagation()}><header><strong id="member-code-title">会员本人核验</strong><button type="button" aria-label="关闭会员码" onClick={onClose}><X size={20} /></button></header>{code ? <><QRCodeSVG value={code} size={220} level="M" /><strong>请向技师或店长出示</strong><p>{seconds} 秒后自动刷新</p><small>动态码每 30 秒更新，仅限本机当次使用，请勿截图或转发。</small></> : <><p>{error || '正在生成会员码…'}</p>{rebindMode ? <><small>验证手机号后将在此浏览器启用会员核验，原入口立即失效。</small><button type="button" onClick={() => void sendPhoneCode(phone).then(() => setRebindMode(true))}>获取验证码</button><input aria-label="短信验证码" inputMode="numeric" maxLength={6} value={rebindCode} onChange={(event) => setRebindCode(event.target.value.replace(/\D/g, '').slice(0, 6))} placeholder="输入 6 位验证码" /><button type="button" disabled={rebindCode.length !== 6} onClick={() => void enableHere()}>验证并在此浏览器启用</button></> : error && <button type="button" onClick={() => void load()}>重新生成</button>}</>}</section></div>;
}

function SelectionList({ sessions, filter, onContinue, onOpen, onFeedback }: { sessions: SelectionSession[]; filter: RecordFilter; onContinue: () => void; onOpen: (record: SelectionSession) => void; onFeedback: (record: SelectionSession) => void }) {
  if (!sessions.length) return <div className="profile-record-empty" role="status"><ReceiptText size={27} aria-hidden="true" /><p>{filter === 'pending-feedback' ? '目前没有待评价的服务' : filter === 'in-service' ? '目前没有进行中的服务' : filter === 'completed' ? '还没有已完成的服务' : '还没有服务记录'}</p><small>{filter === 'pending-feedback' ? '可评价的服务会出现在这里。' : '到店选择项目后，可在这里查看服务进展。'}</small><button type="button" onClick={onContinue}>去选项目<ChevronRight size={14} /></button></div>;
  return <ul className="profile-service-list">{sessions.map(session => <li key={session.id}>
    <button className="profile-record-main" type="button" onClick={() => onOpen(session)} aria-label={`查看${session.items[0]?.name || '到店服务'}详情`}>
      <span className="profile-record-title"><strong>{session.items[0]?.name || '本次到店服务'}{session.items.length > 1 && <small>等{session.items.length}项</small>}</strong><span className={session.can_evaluate && !session.evaluated ? 'needs-feedback' : ''}>{session.can_evaluate && !session.evaluated ? '待评价' : session.service_completed_at ? '已完成' : selectionStatusLabel(session.status)}</span></span>
      <span className="profile-record-summary"><time>{formatDateTime(session.submitted_at) || '到店选购'}</time><span>{formatMoney(selectionDisplayAmount(session))}<ChevronRight size={15} aria-hidden="true" /></span></span>
    </button>
    {session.can_evaluate && !session.evaluated && <div className="profile-record-action"><span>这次体验如何？</span><button type="button" onClick={() => onFeedback(session)}>去评价</button></div>}
  </li>)}</ul>;
}

function RecordDetail({ record, onClose, onFeedback }: { record: SelectionSession; onClose: () => void; onFeedback: () => void }) {
  return <div className="profile-detail-backdrop" role="presentation" onClick={onClose}><section className="profile-detail" role="dialog" aria-modal="true" aria-labelledby="record-detail-title" onClick={(event) => event.stopPropagation()}><header><button type="button" aria-label="关闭到店详情" onClick={onClose}><X size={20} /></button><strong id="record-detail-title">到店详情</strong><span /></header><div className="profile-detail-body"><div className="profile-detail-status"><BadgeCheck size={24} /><strong>{record.can_evaluate && !record.evaluated ? '服务已完成，待评价' : record.service_completed_at ? '本次服务已完成' : selectionStatusLabel(record.status)}</strong><small>{formatDateTime(record.service_completed_at || record.submitted_at)}</small></div><section><h3>服务项目</h3>{record.items.map((item, index) => <div className="profile-detail-item" key={`${item.project_id}-${index}`}><span>{item.name || '到店服务'}</span><strong>×{Math.max(1, item.quantity || 1)}</strong></div>)}</section><section><h3>价格记录</h3><div className="profile-detail-price"><span>门店价 {formatMoney(record.store_total_cents)}</span><span>会员价 {formatMoney(record.member_total_cents)}</span><strong>本次记录 {formatMoney(selectionDisplayAmount(record))}</strong></div></section><p className="profile-detail-note">金额以当次提交和门店确认的服务清单为准。</p></div>{record.can_evaluate && !record.evaluated && <footer><button type="button" onClick={onFeedback}>评价本次服务</button></footer>}</section></div>;
}

function CouponList({ coupons, token }: { coupons: MyCoupon[]; token: string }) {
  const [qr, setQr] = useState<{ couponId: number; token: string; expiresAt: string } | null>(null);
  const [qrBusy, setQrBusy] = useState(false);
  const [qrError, setQrError] = useState('');
  const [qrRemaining, setQrRemaining] = useState(0);
  useEffect(() => {
    if (!qr) { setQrRemaining(0); return undefined; }
    const expiresAt = Date.parse(qr.expiresAt);
    const tick = () => setQrRemaining(Number.isFinite(expiresAt) ? Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000)) : 0);
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [qr]);
  const showQr = async (coupon: MyCoupon) => {
    if (qrBusy || !token) return;
    setQrBusy(true); setQrError('');
    try {
      const result = await getCouponRedeemToken(coupon.id, token);
      setQr({ couponId: coupon.id, token: result.token, expiresAt: result.expires_at });
    } catch (failure) {
      setQrError(failure instanceof Error ? failure.message : '核销码生成失败，请重试');
    } finally { setQrBusy(false); }
  };
  if (!coupons.length) return <p className="profile-empty">券包还是空的</p>;
  return (
    <ul className="profile-list">
      {coupons.map((coupon) => (
        <li key={coupon.id} className={`profile-coupon ${coupon.status}`}>
          <div className="profile-coupon-amount">
            {coupon.coupon_type === 'percent' ? `${(coupon.percent_off / 10)}折` : formatMoney(coupon.amount_cents)}
          </div>
          <div className="profile-coupon-copy">
            <strong>{coupon.name}</strong>
            {coupon.scope_note && <small>{coupon.scope_note}</small>}
            <small>{coupon.min_spend_cents > 0 ? `满 ${formatMoney(coupon.min_spend_cents)} 可用` : '无门槛'}{coupon.expire_at ? ` · ${formatDateTime(coupon.expire_at)} 前有效` : ''}</small>
            {coupon.status === 'unused' && <button type="button" className="profile-coupon-qr-button" disabled={qrBusy} onClick={() => void showQr(coupon)}>{qrBusy ? '生成中…' : '核销码'}</button>}
            {qr?.couponId === coupon.id && qrRemaining > 0 && <div className="profile-coupon-qr">
              <QRCodeSVG value={`${window.location.origin}/technician/store?coupon=${encodeURIComponent(qr.token)}`} size={168} />
              <small>请店长扫码，{Math.floor(qrRemaining / 60)}:{String(qrRemaining % 60).padStart(2, '0')} 内有效</small>
              <div className="profile-coupon-qr-actions">
                <button type="button" onClick={() => { void navigator.clipboard?.writeText(qr.token); }}>复制核销码</button>
                <button type="button" onClick={() => setQr(null)}>收起</button>
              </div>
            </div>}
            {qr?.couponId === coupon.id && qrRemaining <= 0 && <div className="profile-coupon-qr expired">
              <small>核销码已过期，请重新生成。</small>
              <div className="profile-coupon-qr-actions">
                <button type="button" disabled={qrBusy} onClick={() => void showQr(coupon)}>{qrBusy ? '生成中…' : '重新生成'}</button>
                <button type="button" onClick={() => setQr(null)}>收起</button>
              </div>
            </div>}
            {qrError && <small className="profile-coupon-error">{qrError}</small>}
          </div>
          <span className="profile-status">{couponStatusLabel(coupon.status)}</span>
        </li>
      ))}
    </ul>
  );
}

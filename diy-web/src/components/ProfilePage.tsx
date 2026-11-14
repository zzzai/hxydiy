import { ArrowLeft, BadgeCheck, Bookmark, CalendarDays, ChevronRight, Clock3, LogOut, MessageSquareText, ReceiptText, Store, UserRound, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';

import { ApiError, cancelOrder, enrollTrustedDevice, getCouponRedeemToken, getMyCoupons, getMySelectionSessions, issueMemberCode, loginByPhone, rebindTrustedDevice, sendPhoneCode, submitCustomerFeedback, type CustomerConsumptionOverview, type CustomerMembershipOverview, type MyCoupon, type Order, type SelectionSession } from '../api';
import { authFailureAction, clearCustomerAuth, isValidPhone, normalizePhone, writeCustomerAuth, type CustomerAuth, type CustomerUser } from '../customerAuth';
import { formatMemberCents, formatMoney } from '../domain';
import { useCustomerMembership } from './useCustomerMembership';
import { useCustomerConsumption } from './useCustomerConsumption';
import { customerLoginCopy, shouldShowCouponTab } from '../customerCopy';
import { bindPendingGuestCoupons } from '../guestCoupon';
import { canSelfCancelOrder, couponStatusLabel, formatDateTime, membershipState, orderStatusLabel, recordFilter, selectionDisplayAmount, selectionStatusLabel, type RecordFilter } from '../profile';
import MembershipBanner from './MembershipBanner';
import FeedbackDialog from './FeedbackDialog';
import MyReports from './MyReports';
import { ProfileReturnTools, ReturnDialog } from './CustomerReturnTools';
import './profile-home.css';

type TabKey = 'records' | 'coupons';

// Temporary customer presentation switches; server rules and records remain intact.
const SHOW_PROFILE_HISTORY = true;
const SHOW_DYNAMIC_MEMBER_CODE = false;
const OPEN_COUPON_ON_MOUNT = typeof window !== 'undefined'
  && new URLSearchParams(window.location.search).get('coupon') === '1';

export default function ProfilePage({ open, auth, onClose, onAuthChange, initialReportsOpen = false, onReportsBack, onOpenReports, storeId = 1, refreshKey = 0 }: {
  open: boolean;
  auth: CustomerAuth | null;
  onClose: () => void;
  onAuthChange: (auth: CustomerAuth | null) => void;
  initialReportsOpen?: boolean;
  onReportsBack?: () => void;
  onOpenReports?: () => void;
  storeId?: number;
  refreshKey?: number;
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
    <div className={`profile-page ${reportsOpen ? 'profile-report-view' : 'profile-home'}`} role="dialog" aria-modal="true" aria-label="个人中心">
      <header>
        <button type="button" aria-label={reportsOpen ? onReportsBack ? '返回首页' : '返回我的' : '返回'} onClick={reportsOpen ? onReportsBack || (() => setReportsOpen(false)) : onClose}><ArrowLeft size={22} /></button>
        <strong>{reportsOpen ? '我的检测报告' : '我的'}</strong>
        {auth ? <button className="profile-logout" type="button" onClick={() => { clearCustomerAuth(); onAuthChange(null); }}><LogOut size={15} />退出登录</button> : <span />}
      </header>

      {!auth
        ? <div className="profile-anonymous-body">{reportsOpen ? <p className="my-reports-note">我的检测报告：请先验证检测时使用的手机号。</p> : <button className="profile-pending-task" type="button" onClick={openReports}><span><ReceiptText size={19} /><strong>我的检测报告</strong><small>验证手机号后查看本人结果</small></span><ChevronRight size={18} /></button>}<ProfileLogin onAuthChange={onAuthChange} />{!reportsOpen && <ProfileReturnTools storeId={storeId} compact />}</div>
        : reportsOpen ? <MyReports key={auth.token} token={auth.token} onVerify={() => { clearCustomerAuth(); onAuthChange(null); }} /> : (
          <main className="profile-body">
            <ProfileCard user={auth.user} onShowCode={() => setMemberCodeOpen(true)} />
            <MembershipSnapshot data={membership.data} loading={membership.loading} error={membership.error} onRetry={membership.retry} />
            <ConsumptionHistory bills={consumption.bills} data={consumption.data} loading={consumption.loading} loadingMore={consumption.loadingMore} hasMore={consumption.hasMore} error={consumption.error} onRetry={consumption.retry} onLoadMore={consumption.loadMore} />
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
            <ReturnDialog panel={returnPanel} storeId={storeId} onClose={() => setReturnPanel(null)} />
            {SHOW_DYNAMIC_MEMBER_CODE && memberCodeOpen && <MemberCodeDialog token={auth.token} phone={auth.user.phone} onTokenReplaced={(token) => { const next = { ...auth, token }; writeCustomerAuth(next); onAuthChange(next); }} onClose={() => setMemberCodeOpen(false)} />}
          </main>
        )}
    </div>
  );
}

function ProfileLogin({ onAuthChange }: { onAuthChange: (auth: CustomerAuth) => void }) {
  const copy = customerLoginCopy('profile');
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [seconds, setSeconds] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (seconds <= 0) return undefined;
    const timer = window.setTimeout(() => setSeconds((value) => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [seconds]);

  const send = async () => {
    if (!isValidPhone(phone)) return setError('请输入正确的手机号');
    setBusy(true);
    setError('');
    try {
      await sendPhoneCode(phone);
      setSeconds(60);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '验证码发送失败');
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    if (!isValidPhone(phone) || code.length !== 6) return setError('请输入手机号和 6 位验证码');
    setBusy(true);
    setError('');
    try {
      const result = await loginByPhone(phone, code);
      writeCustomerAuth(result);
      await bindPendingGuestCoupons(result.token);
      onAuthChange(result);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : reason instanceof Error ? reason.message : '登录失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="profile-login">
      <section className="profile-login-hero">
        <UserRound size={30} />
        <div><h1>{copy.title}</h1><p>{copy.detail}</p></div>
      </section>
      <section className="coupon-login-form">
        <label><span>手机号</span><input value={phone} inputMode="tel" placeholder="请输入手机号" onChange={(event) => setPhone(normalizePhone(event.target.value))} /></label>
        <label><span>验证码</span><div><input value={code} inputMode="numeric" maxLength={6} placeholder="6 位验证码" onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))} /><button type="button" disabled={busy || seconds > 0} onClick={send}>{seconds > 0 ? `${seconds}s` : '获取验证码'}</button></div></label>
      </section>
      {error && <p className="coupon-login-error">{error}</p>}
      <button className="profile-login-submit" type="button" disabled={busy} onClick={confirm}>{busy ? '正在登录' : copy.action}</button>
    </main>
  );
}

function ProfileCard({ user, onShowCode }: { user: CustomerUser; onShowCode: () => void }) {
  const state = membershipState(user.member_expire_at);
  const expiry = user.member_expire_at ? formatDateTime(user.member_expire_at).slice(0, 10) : '';
  const memberLabel = user.member_type === 'annual' ? '年度权益卡' : user.member_type === 'stored' ? '储值会员卡' : '会员身份';
  return <section className={`profile-identity-card ${user.is_member ? 'is-member' : 'is-guest'}`} aria-label="我的会员信息">
    {user.is_member && <div className="profile-card-heading"><strong>荷小悦会员</strong><span className="profile-member-label"><BadgeCheck size={15} aria-hidden="true" />{memberLabel}</span></div>}
    <div className="profile-avatar"><UserRound size={24} aria-hidden="true" /></div>
    <div className="profile-identity-copy"><h1>{user.nickname || '荷小悦顾客'}</h1><p>{maskPhone(user.phone)}</p></div>
    {user.is_member && <p className="profile-membership-expiry">{state.kind === 'expired' ? '会员权益已到期' : expiry ? `权益有效期至 ${expiry}` : '会员有效期以门店记录为准'}{state.kind === 'expiring' && <span> · 还有 {state.daysLeft} 天</span>}</p>}
    {SHOW_DYNAMIC_MEMBER_CODE && user.is_member && state.kind !== 'expired' && <button className="profile-member-code-button" type="button" onClick={onShowCode}>出示动态会员码</button>}
  </section>;
}

function MembershipSnapshot({ data, loading, error, onRetry }: { data: CustomerMembershipOverview | null; loading: boolean; error: string; onRetry: () => void }) {
  if (loading) return <section className="profile-membership-detail" aria-label="会员卡与权益"><p className="profile-membership-loading" role="status">正在读取会员卡快照…</p></section>;
  if (error) return <section className="profile-membership-detail" aria-label="会员卡与权益"><p className="profile-membership-error" role="alert">{error}</p><button type="button" className="profile-membership-retry" onClick={onRetry}>重新加载</button></section>;
  if (!data) return null;
  return <section className="profile-membership-detail" aria-label="会员卡与权益">
    <div className="profile-membership-heading"><div><h2>会员卡与权益</h2><small>余额为来源快照，具体构成以门店记录为准</small></div><span>{data.card_count > 0 ? `${data.card_count} 张来源卡` : '暂无来源卡'}</span></div>
    {data.cards.length === 0 ? <p className="profile-membership-empty">{data.identity.is_member ? '当前没有可展示的本店来源卡，权益以门店记录为准。' : '暂未关联本店来源会员卡。'}</p> : <ul className="profile-membership-cards">
      {data.cards.map(card => <li key={card.id} className={`profile-membership-card ${card.usable ? 'is-usable' : 'is-inactive'}`}>
        <div className="profile-membership-card-head"><strong>{card.card_type_label}</strong><span>{membershipCardStatusLabel(card.status)}</span></div>
        <p>{card.store_name || `门店 #${card.store_id}`} · {card.usable ? (card.balance.reconciliation === 'zero_balance_against_active_card_review' ? '状态待门店核实' : '当前可用') : '当前不可用'}</p>
        <small>{card.expires_at ? `有效期至 ${formatDateTime(card.expires_at).slice(0, 10)}` : '有效期以来源记录为准'}{card.observed_at ? ` · 核验于 ${formatDateTime(card.observed_at).slice(0, 10)}` : ' · 核验时间未记录'}</small>
        {card.card_type === 'stored' && <div className="profile-membership-balance">
          <span>{card.balance.evidence === 'balance_snapshot' ? '余额观测' : '来源余额快照'}</span>
          <strong>{card.balance.amount_cents !== null ? formatMemberCents(card.balance.amount_cents) : '未核实'}</strong>
          {card.balance.split === 'verified' && card.balance.principal_cents !== null && card.balance.bonus_cents !== null && <small>本金 {formatMemberCents(card.balance.principal_cents)} · 赠金 {formatMemberCents(card.balance.bonus_cents)}</small>}
          <small>{card.balance.status === 'conflicted' ? '同一观测时间存在冲突，余额未核实（不按首次或任一取值）' : card.balance.status === 'anomaly' ? '余额观测异常，未核实' : card.balance.reconciliation === 'zero_balance_against_active_card_review' ? '余额观测为 0，状态待门店核实' : card.balance.evidence === 'balance_snapshot' ? '非实时观测，总额不等于本金，未知不计为 0' : '非实时余额，具体构成以门店记录为准'}{card.balance.observed_at ? ` · 观测于 ${formatDateTime(card.balance.observed_at).slice(0, 10)}` : ''}</small>
          {card.balance.original && <small>原始快照 {formatMemberCents(card.balance.original.amount_cents)}{card.balance.original.observed_at ? `（${formatDateTime(card.balance.original.observed_at).slice(0, 10)}）` : ''}</small>}
        </div>}
        <details className="profile-membership-benefits"><summary>查看权益</summary><ul>{card.benefits.map(benefit => <li key={benefit}>{benefit}</li>)}</ul><small>{card.benefits_note}</small></details>
      </li>)}
    </ul>}
    <p className="profile-membership-scope">{data.coverage.card_snapshot === 'returned' ? '会员卡信息为来源快照' : '暂无来源会员卡'}{data.coverage.as_of ? `，截至 ${formatDateTime(data.coverage.as_of).slice(0, 10)}` : ''}。</p>
  </section>;
}

function ConsumptionHistory({ bills, data, loading, loadingMore, hasMore, error, onRetry, onLoadMore }: { bills: CustomerConsumptionOverview['bills']; data: CustomerConsumptionOverview | null; loading: boolean; loadingMore: boolean; hasMore: boolean; error: string; onRetry: () => void; onLoadMore: () => void }) {
  if (loading) return <section className="profile-consumption" aria-label="历史消费"><p className="profile-membership-loading" role="status">正在读取消费记录…</p></section>;
  if (error && !bills.length) return <section className="profile-consumption" aria-label="历史消费"><p className="profile-membership-error" role="alert">{error}</p><button type="button" className="profile-membership-retry" onClick={onRetry}>重新加载</button></section>;
  if (!data) return null;
  const hasBills = bills.length > 0;
  const range = data.coverage.query_range_start && data.coverage.query_range_end
    ? `${formatDateTime(data.coverage.query_range_start).slice(0, 10)} ~ ${formatDateTime(data.coverage.query_range_end).slice(0, 10)}`
    : null;
  const observed = data.coverage.observed_at ? `观测 ${formatDateTime(data.coverage.observed_at).slice(0, 10)}` : '';
  const coverageLabel = data.coverage.complete === true ? '覆盖完整' : data.coverage.complete === false ? (data.coverage.coverage_gaps ? '存在缺失，覆盖不完整' : '覆盖不完整') : '覆盖未核实';
  return <section className="profile-consumption" aria-label="历史消费">
    <div className="profile-membership-heading"><div><h2>历史消费</h2><small>来源可核实记录，独立于 DIY 钱包</small></div><span>{data.pagination.total} 笔记录</span></div>
    {!hasBills
      ? <p className="profile-membership-empty">暂无可核实的来源消费记录{data.coverage.conflict_bill_groups > 0 ? `（${data.coverage.conflict_bill_groups} 组待核对）` : ''}。</p>
      : <>
        <div className="profile-consumption-savings"><span>累计消费优惠</span><strong>{data.savings.amount_cents !== null ? formatMemberCents(data.savings.amount_cents) : '未核实'}</strong><small>{data.savings.note}</small></div>
        <ul className="profile-consumption-bills">
          {bills.map(bill => <li key={bill.id} className="profile-consumption-bill">
            <div><strong>{bill.source_bill_no}</strong><span>{bill.savings.amount_cents !== null ? `优惠 ${formatMemberCents(bill.savings.amount_cents)}` : '优惠未核实'}</span></div>
            <small>{bill.occurred_at ? `消费于 ${formatDateTime(bill.occurred_at).slice(0, 10)}` : '时间未记录'}{bill.settled_total_cents !== null ? ` · 结算 ${formatMemberCents(bill.settled_total_cents, bill.currency)}` : ''}</small>
            {bill.lines.length > 0 && <details><summary>查看明细</summary><ul>{bill.lines.map((line, i) => <li key={i}>{line.description}{line.quantity !== null ? ` × ${line.quantity}` : ''}{line.settled_cents !== null ? ` · ${formatMemberCents(line.settled_cents, bill.currency)}` : ''}</li>)}</ul></details>}
          </li>)}
        </ul>
        {hasMore && <button type="button" className="profile-consumption-more" onClick={onLoadMore} disabled={loadingMore}>{loadingMore ? '加载中…' : '加载更多'}</button>}
        {error && hasBills && <p className="profile-membership-error" role="alert">{error}</p>}
      </>}
    <p className="profile-consumption-scope">统计覆盖期：{range ?? '未记录'}{observed ? ` · ${observed}` : ''}；{coverageLabel}；金额未核实不计入。</p>
  </section>;
}

function membershipCardStatusLabel(status: string) {
  return status === 'active' ? '有效' : status === 'disabled' ? '已停用' : status === 'expired' ? '已到期' : status === 'exhausted' ? '余额用尽' : status === 'scheduled' ? '未开始' : '待核实';
}

function maskPhone(phone: string) {
  const normalized = phone.replace(/\D/g, '');
  return normalized.length === 11 ? `${normalized.slice(0, 3)}****${normalized.slice(-4)}` : '手机号已绑定';
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

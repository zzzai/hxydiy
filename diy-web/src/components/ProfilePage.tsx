import { ArrowLeft, BadgeCheck, ChevronRight, Clock3, LogOut, MessageSquareText, ReceiptText, Ticket, UserRound, X } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { ApiError, cancelOrder, getMyCoupons, getMyOrders, getMySelectionSessions, loginByPhone, sendPhoneCode, submitCustomerFeedback, type MyCoupon, type Order, type SelectionSession } from '../api';
import { authFailureAction, clearCustomerAuth, isValidPhone, normalizePhone, writeCustomerAuth, type CustomerAuth, type CustomerUser } from '../customerAuth';
import { formatMoney } from '../domain';
import { customerLoginCopy, shouldShowCouponTab } from '../customerCopy';
import { canSelfCancelOrder, couponStatusLabel, formatDateTime, membershipSavingCents, membershipState, orderStatusLabel, recordFilter, selectionDisplayAmount, selectionStatusLabel, type RecordFilter } from '../profile';
import MembershipBanner from './MembershipBanner';
import FeedbackDialog from './FeedbackDialog';

type TabKey = 'records' | 'coupons';

export default function ProfilePage({ open, auth, onClose, onAuthChange }: {
  open: boolean;
  auth: CustomerAuth | null;
  onClose: () => void;
  onAuthChange: (auth: CustomerAuth | null) => void;
}) {
  const [tab, setTab] = useState<TabKey>('records');
  const [recordState, setRecordState] = useState<RecordFilter>('all');
  const [selectedRecord, setSelectedRecord] = useState<SelectionSession | null>(null);
  const [feedbackRecord, setFeedbackRecord] = useState<SelectionSession | null>(null);
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const [orders, setOrders] = useState<Order[]>([]);
  const [sessions, setSessions] = useState<Awaited<ReturnType<typeof getMySelectionSessions>>>([]);
  const [coupons, setCoupons] = useState<MyCoupon[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [cancelling, setCancelling] = useState(false);

  const loadData = useCallback((token: string, isMember: boolean) => {
    setLoading(true);
    setLoadError('');
    Promise.all([
      getMyOrders(token),
      getMySelectionSessions(token),
      // 会员不展示券入口，也不应请求会员无权限的券接口；否则任一 403 会让整个个人中心误报加载失败。
      isMember ? Promise.resolve([] as MyCoupon[]) : getMyCoupons(token),
    ]).then(([orderItems, sessionItems, couponItems]) => {
      setOrders(orderItems);
      setSessions(sessionItems);
      setCoupons(couponItems);
    }).catch((reason) => {
      if (['reauthenticate', 'session-replaced'].includes(authFailureAction(reason))) {
        clearCustomerAuth();
        onAuthChange(null);
        return;
      }
      setLoadError(reason instanceof Error ? reason.message : '加载失败，请稍后重试');
    }).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!open || !auth) return;
    loadData(auth.token, auth.user.is_member);
  }, [open, auth, loadData]);

  useEffect(() => { if (auth?.user.is_member && tab === 'coupons') setTab('records'); }, [auth?.user.is_member, tab]);

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
    <div className="profile-page" role="dialog" aria-modal="true" aria-label="个人中心">
      <header>
        <button type="button" aria-label="返回" onClick={onClose}><ArrowLeft size={22} /></button>
        <strong>我的</strong>
        {auth ? <button className="profile-logout" type="button" onClick={() => { clearCustomerAuth(); onAuthChange(null); }}><LogOut size={15} />退出登录</button> : <span />}
      </header>

      {!auth
        ? <ProfileLogin onAuthChange={onAuthChange} />
        : (
          <main className="profile-body">
            <ProfileCard user={auth.user} savingCents={membershipSavingCents(sessions)} completedCount={sessions.filter((item) => item.service_completed_at).length} />
            {sessions.some((item) => item.can_evaluate && !item.evaluated) && <button className="profile-pending-task" type="button" onClick={() => { setTab('records'); setRecordState('pending-feedback'); }}><span><MessageSquareText size={19} /><strong>待评价 {sessions.filter((item) => item.can_evaluate && !item.evaluated).length}</strong><small>完成评价，帮助我们改进服务</small></span><ChevronRight size={18} /></button>}
            {!auth.user.is_member && <MembershipBanner />}
            <nav className="profile-tabs" aria-label="个人中心板块">
              <TabButton active={tab === 'records'} onClick={() => setTab('records')} icon={<Clock3 size={15} />} label="到店记录" count={sessions.length} />
              {shouldShowCouponTab(auth.user.is_member) && <TabButton active={tab === 'coupons'} onClick={() => setTab('coupons')} icon={<Ticket size={15} />} label="我的券" count={coupons.length} />}
            </nav>
            {loadError && <p className="profile-error">{loadError}</p>}
            {loading && <p className="profile-empty">正在加载…</p>}
            {!loading && !loadError && (
              tab === 'records' ? <><RecordFilters value={recordState} onChange={setRecordState} /><SelectionList sessions={recordFilter(sessions, recordState)} onContinue={onClose} onOpen={setSelectedRecord} onFeedback={setFeedbackRecord} /></>
                : shouldShowCouponTab(auth.user.is_member) ? <CouponList coupons={coupons} /> : <OrderList orders={orders} cancelling={cancelling} onCancel={handleCancelOrder} />
            )}
            {selectedRecord && <RecordDetail record={selectedRecord} onClose={() => setSelectedRecord(null)} onFeedback={() => { setFeedbackRecord(selectedRecord); setSelectedRecord(null); }} />}
            <FeedbackDialog open={Boolean(feedbackRecord)} submitting={feedbackSubmitting} submitted={Boolean(feedbackRecord?.evaluated)} onClose={() => setFeedbackRecord(null)} onSubmit={async (input) => { if (!auth || !feedbackRecord) return; setFeedbackSubmitting(true); try { await submitCustomerFeedback(feedbackRecord.id, auth.token, input); setFeedbackRecord(null); loadData(auth.token, auth.user.is_member); } finally { setFeedbackSubmitting(false); } }} />
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

function ProfileCard({ user, savingCents, completedCount }: { user: CustomerUser; savingCents: number; completedCount: number }) {
  const state = membershipState(user.member_expire_at);
  const expiry = user.member_expire_at ? formatDateTime(user.member_expire_at).slice(0, 10) : '';
  return (
    <section className={`profile-card ${user.is_member ? 'is-member' : 'is-guest'}`}>
      <div className="profile-avatar"><UserRound size={22} /></div>
      <div className="profile-account">
        <strong>{user.nickname || (user.is_member ? '荷小悦年度会员' : '荷小悦顾客')}</strong>
        <small>{maskPhone(user.phone)} · {user.is_member ? '年度权益卡会员' : '普通顾客'}</small>
      </div>
      <div className="profile-identity">
        {user.is_member ? <><BadgeCheck size={17} /><span>会员价</span></> : <span>到店服务</span>}
      </div>
      {user.is_member && <div className="profile-member-value"><div><small>{state.kind === 'expired' ? '会员权益已到期' : `有效期至 ${expiry || '以门店记录为准'}`}</small>{state.kind === 'expiring' && <em>还有 {state.daysLeft} 天到期</em>}</div><div><small>累计会员省</small><strong>{completedCount ? formatMoney(savingCents) : '完成首次服务后可查看'}</strong><span>{completedCount ? `已完成 ${completedCount} 次服务` : '按已完成服务价格快照计算'}</span></div></div>}
      {!user.is_member && <p className="profile-card-benefit">到店办理年度权益卡，开通后享会员价</p>}
    </section>
  );
}

function maskPhone(phone: string) {
  const normalized = phone.replace(/\D/g, '');
  return normalized.length === 11 ? `${normalized.slice(0, 3)}****${normalized.slice(-4)}` : '手机号已绑定';
}

function TabButton({ active, onClick, icon, label, count }: {
  active: boolean; onClick: () => void; icon: React.ReactNode; label: string; count: number;
}) {
  return (
    <button type="button" className={active ? 'active' : ''} onClick={onClick}>
      {icon}<span>{label}</span>{count > 0 && <em>{count}</em>}
    </button>
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
  return <div className="profile-record-filters" aria-label="到店记录筛选">{([['all', '全部'], ['pending-feedback', '待评价'], ['in-service', '服务中'], ['completed', '已完成']] as const).map(([key, label]) => <button key={key} type="button" className={value === key ? 'active' : ''} aria-pressed={value === key} onClick={() => onChange(key)}>{label}</button>)}</div>;
}

function SelectionList({ sessions, onContinue, onOpen, onFeedback }: { sessions: Awaited<ReturnType<typeof getMySelectionSessions>>; onContinue: () => void; onOpen: (record: SelectionSession) => void; onFeedback: (record: SelectionSession) => void }) {
  if (!sessions.length) return <p className="profile-empty">还没有到店选单记录。</p>;
  return (
    <ul className="profile-list">
      {sessions.map((session) => (
        <li key={session.id} className="profile-order profile-selection-record" tabIndex={0} role="button" onClick={() => onOpen(session)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onOpen(session); } }}>
          <div className="profile-list-head profile-record-store">
            <strong><span className="profile-record-badge">到店</span>荷小悦草本服务</strong>
            <span className={`profile-status status-${session.status}`}>{session.can_evaluate && !session.evaluated ? '待评价' : session.service_completed_at ? '已完成' : selectionStatusLabel(session.status)}</span>
          </div>
          <div className="profile-record-product">
            <div className="profile-record-thumb"><ReceiptText size={22} /></div>
            <div className="profile-record-product-copy">
              <strong>{session.items[0]?.name || '本次到店服务'}</strong>
              <small>{session.items.length > 1 ? `${session.items[0]?.name || '服务项目'}等 ${session.items.length} 项` : '按本次服务清单记录'}</small>
            </div>
            <span className="profile-record-quantity">×{session.items.reduce((sum, item) => sum + Math.max(1, item.quantity || 1), 0)}</span>
          </div>
          <div className="profile-record-meta"><span>{formatDateTime(session.submitted_at) || '到店扫码选购'}</span><strong>共计 {formatMoney(selectionDisplayAmount(session))}</strong></div>
          <div className="profile-record-actions">{session.can_evaluate && !session.evaluated && <button type="button" onClick={(event) => { event.stopPropagation(); onFeedback(session); }}>去评价</button>}<button type="button" onClick={(event) => { event.stopPropagation(); onContinue(); }}>再次选购</button><span aria-hidden="true"><ChevronRight size={17} /></span></div>
        </li>
      ))}
    </ul>
  );
}

function RecordDetail({ record, onClose, onFeedback }: { record: SelectionSession; onClose: () => void; onFeedback: () => void }) {
  return <div className="profile-detail-backdrop" role="presentation" onClick={onClose}><section className="profile-detail" role="dialog" aria-modal="true" aria-labelledby="record-detail-title" onClick={(event) => event.stopPropagation()}><header><button type="button" aria-label="关闭到店详情" onClick={onClose}><X size={20} /></button><strong id="record-detail-title">到店详情</strong><span /></header><div className="profile-detail-body"><div className="profile-detail-status"><BadgeCheck size={24} /><strong>{record.can_evaluate && !record.evaluated ? '服务已完成，待评价' : record.service_completed_at ? '本次服务已完成' : selectionStatusLabel(record.status)}</strong><small>{formatDateTime(record.service_completed_at || record.submitted_at)}</small></div><section><h3>服务项目</h3>{record.items.map((item, index) => <div className="profile-detail-item" key={`${item.project_id}-${index}`}><span>{item.name || '到店服务'}</span><strong>×{Math.max(1, item.quantity || 1)}</strong></div>)}</section><section><h3>价格记录</h3><div className="profile-detail-price"><span>门店价 {formatMoney(record.store_total_cents)}</span><span>会员价 {formatMoney(record.member_total_cents)}</span><strong>本次记录 {formatMoney(selectionDisplayAmount(record))}</strong></div></section><p className="profile-detail-note">金额以当次提交和门店确认的服务清单为准。</p></div>{record.can_evaluate && !record.evaluated && <footer><button type="button" onClick={onFeedback}>评价本次服务</button></footer>}</section></div>;
}

function CouponList({ coupons }: { coupons: MyCoupon[] }) {
  if (!coupons.length) return <p className="profile-empty">暂无优惠券</p>;
  return (
    <ul className="profile-list">
      {coupons.map((coupon) => (
        <li key={coupon.id} className={`profile-coupon ${coupon.status}`}>
          <div className="profile-coupon-amount">
            {coupon.coupon_type === 'percent' ? `${coupon.percent_off}%` : formatMoney(coupon.amount_cents)}
          </div>
          <div className="profile-coupon-copy">
            <strong>{coupon.name}</strong>
            <small>{coupon.min_spend_cents > 0 ? `满 ${formatMoney(coupon.min_spend_cents)} 可用` : '无门槛'}{coupon.expire_at ? ` · ${formatDateTime(coupon.expire_at)} 前有效` : ''}</small>
          </div>
          <span className="profile-status">{couponStatusLabel(coupon.status)}</span>
        </li>
      ))}
    </ul>
  );
}

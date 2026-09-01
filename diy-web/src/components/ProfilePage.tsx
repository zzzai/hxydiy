import { ArrowLeft, BadgeCheck, Clock3, LogOut, ReceiptText, Ticket, UserRound } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { ApiError, cancelOrder, getMyCoupons, getMyOrders, getMySelectionSessions, loginByPhone, sendPhoneCode, type MyCoupon, type Order } from '../api';
import { authFailureAction, clearCustomerAuth, isValidPhone, normalizePhone, writeCustomerAuth, type CustomerAuth, type CustomerUser } from '../customerAuth';
import { formatMoney } from '../domain';
import { customerLoginCopy, shouldShowCouponTab } from '../customerCopy';
import { canSelfCancelOrder, couponStatusLabel, formatDateTime, membershipSavingCents, orderStatusLabel, selectionDisplayAmount, selectionStatusLabel } from '../profile';
import MembershipBanner from './MembershipBanner';

type TabKey = 'orders' | 'selections' | 'coupons';

export default function ProfilePage({ open, auth, onClose, onAuthChange }: {
  open: boolean;
  auth: CustomerAuth | null;
  onClose: () => void;
  onAuthChange: (auth: CustomerAuth | null) => void;
}) {
  const [tab, setTab] = useState<TabKey>('orders');
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
      if (authFailureAction(reason) === 'reauthenticate') {
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

  useEffect(() => {
    if (auth?.user.is_member && tab === 'coupons') setTab('orders');
  }, [auth?.user.is_member, tab]);

  const handleCancelOrder = async (order: Order) => {
    if (!auth || cancelling) return;
    if (!window.confirm(`确认取消服务单 ${order.order_no}？取消后不可恢复。`)) return;
    setCancelling(true);
    try {
      await cancelOrder(order.id, auth.token);
      loadData(auth.token, auth.user.is_member);
    } catch (reason) {
      if (authFailureAction(reason) === 'reauthenticate') {
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
            <ProfileCard user={auth.user} />
            {auth.user.is_member && <div className="profile-saving-banner"><strong>会员价累计预计省下</strong><span>{formatMoney(membershipSavingCents(sessions))}</span><small>按历史到店选单的门店价与会员价差额估算</small></div>}
            {!auth.user.is_member && <MembershipBanner />}
            <nav className="profile-tabs" aria-label="个人中心板块">
              <TabButton active={tab === 'orders'} onClick={() => setTab('orders')} icon={<ReceiptText size={15} />} label="服务记录" count={orders.length} />
              <TabButton active={tab === 'selections'} onClick={() => setTab('selections')} icon={<Clock3 size={15} />} label="到店记录" count={sessions.length} />
              {shouldShowCouponTab(auth.user.is_member) && <TabButton active={tab === 'coupons'} onClick={() => setTab('coupons')} icon={<Ticket size={15} />} label="我的券" count={coupons.length} />}
            </nav>
            {loadError && <p className="profile-error">{loadError}</p>}
            {loading && <p className="profile-empty">正在加载…</p>}
            {!loading && !loadError && (
              tab === 'orders' ? <OrderList orders={orders} cancelling={cancelling} onCancel={handleCancelOrder} />
                : tab === 'selections' ? <SelectionList sessions={sessions} onContinue={onClose} />
                  : shouldShowCouponTab(auth.user.is_member) ? <CouponList coupons={coupons} /> : <OrderList orders={orders} cancelling={cancelling} onCancel={handleCancelOrder} />
            )}
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

function ProfileCard({ user }: { user: CustomerUser }) {
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
      {user.is_member && <p className="profile-card-benefit">全年享会员价 · 周二会员日更优惠</p>}
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

function SelectionList({ sessions, onContinue }: { sessions: Awaited<ReturnType<typeof getMySelectionSessions>>; onContinue: () => void }) {
  if (!sessions.length) return <p className="profile-empty">还没有到店选单记录。</p>;
  return (
    <ul className="profile-list">
      {sessions.map((session) => (
        <li key={session.id} className="profile-order profile-selection-record">
          <div className="profile-list-head profile-record-store">
            <strong><span className="profile-record-badge">到店</span>荷小悦草本服务</strong>
            <span className={`profile-status status-${session.status}`}>{selectionStatusLabel(session.status)}</span>
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
          <div className="profile-record-actions"><button type="button" onClick={onContinue}>再次选购</button><button type="button" onClick={onContinue}>返回菜单</button></div>
        </li>
      ))}
    </ul>
  );
}

function CouponList({ coupons }: { coupons: MyCoupon[] }) {
  if (!coupons.length) return <p className="profile-empty">还没有优惠券。到店可参与领券活动。</p>;
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

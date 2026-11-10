import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Input, Modal, message } from 'antd';
import { AppstoreOutlined, ArrowLeftOutlined, HomeOutlined, ReloadOutlined, ShopOutlined, TeamOutlined, GiftOutlined } from '@ant-design/icons';
import QRCode from 'qrcode';
import { createHalfPriceCouponLink, getManagerDaily, getManagerTeam, getManagerWorkbench, getStaff } from '../api';
import { parseManagerReview, takeManagerPendingOrder, takeManagerPendingReview, type PendingReview } from '../wecomSession';
import { useTechnicianSession } from './useTechnicianSession';
import { isMobileManager } from './managerMobile';
import ManagerTodayView from './ManagerTodayView';
import ManagerDailyOpsView from './ManagerDailyOpsView';
import ManagerTeamView from './ManagerTeamView';
import ManagerPositionView from './ManagerPositionView';
import ManagerTasksView from './ManagerTasksView';
import ManagerServiceOrdersView from './ManagerServiceOrdersView';
import ManagerReviewsView from './ManagerReviewsView';
import ManagerCouponRedeemView from './ManagerCouponRedeemView';
import './manager-mobile.css';
import './manager-p0.css';

type Tab = 'today' | 'floor' | 'team' | 'ops';
type Subview = 'orders' | 'tasks' | 'reviews' | 'coupons' | null;

export default function ManagerP0Page(_props: { learningEntry?: React.ReactNode } = {}) {
  const current = useTechnicianSession();
  const storeId = Number(getStaff()?.store_id || 0);
  const [tab, setTab] = useState<Tab>('today');
  const [subview, setSubview] = useState<Subview>(null);
  const [daily, setDaily] = useState<Awaited<ReturnType<typeof getManagerDaily>>['data'] | null>(null);
  const [team, setTeam] = useState<Awaited<ReturnType<typeof getManagerTeam>>['data'] | null>(null);
  const [workbench, setWorkbench] = useState<Awaited<ReturnType<typeof getManagerWorkbench>>['data'] | null>(null);
  const [loading, setLoading] = useState(true);
  const [couponShare, setCouponShare] = useState<{ link: string; qr: string; issued: number; remaining: number; limit: number } | null>(null);
  const [couponBusy, setCouponBusy] = useState(false);
  const [couponToken, setCouponToken] = useState('');
  const [reviewFocus, setReviewFocus] = useState<PendingReview | null>(null);
  const [mapRefresh, setMapRefresh] = useState(0);
  const [ordersRefresh, setOrdersRefresh] = useState(0);
  const loadingRef = useRef(false);

  const load = useCallback(async (silent = false) => {
    if (!current() || !isMobileManager(getStaff()) || loadingRef.current) return;
    loadingRef.current = true;
    if (!silent) setLoading(true);
    try {
      const [dailyResponse, teamResponse, workbenchResponse] = await Promise.all([
        getManagerDaily(), getManagerTeam(), getManagerWorkbench(),
      ]);
      if (!current()) return;
      setDaily(dailyResponse.data); setTeam(teamResponse.data); setWorkbench(workbenchResponse.data);
    } catch {
      // Keep the last successful snapshot; the page remains usable offline.
    } finally {
      loadingRef.current = false;
      if (current()) setLoading(false);
    }
  }, [current]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const refresh = () => { if (document.visibilityState === 'visible') void load(true); };
    const timer = window.setInterval(refresh, 15000);
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => { window.clearInterval(timer); window.removeEventListener('focus', refresh); document.removeEventListener('visibilitychange', refresh); };
  }, [load]);

  useEffect(() => {
    const coupon = new URLSearchParams(window.location.search).get('coupon');
    if (coupon) { setCouponToken(coupon); setSubview('coupons'); return; }
    const directReview = new URLSearchParams(window.location.search).get('review');
    const pendingReview = takeManagerPendingReview();
    const review = parseManagerReview(directReview) || pendingReview;
    if (review) { setReviewFocus(review); setSubview('reviews'); return; }
    if (new URLSearchParams(window.location.search).get('order') || takeManagerPendingOrder()) setSubview('orders');
  }, []);

  const generateCoupon = async () => {
    if (couponBusy) return;
    setCouponBusy(true);
    try {
      const response = await createHalfPriceCouponLink();
      const url = new URL('/', window.location.origin);
      if (storeId > 0) url.searchParams.set('store', String(storeId));
      url.searchParams.set('c', response.data.code || response.data.token);
      const link = url.toString();
      let qr = '';
      try { qr = await QRCode.toDataURL(link, { width: 220, margin: 1, errorCorrectionLevel: 'L' }); } catch { /* link still works */ }
      setCouponShare({ link, qr, issued: response.data.issued, remaining: response.data.remaining, limit: response.data.limit });
    } catch (failure) {
      const detail = (failure as { response?: { data?: { detail?: { message?: string } } } })?.response?.data?.detail;
      message.error(detail?.message || '生成券链接失败，请重试');
    } finally {
      setCouponBusy(false);
    }
  };

  const openTab = (next: Tab) => { setSubview(null); setTab(next); };
  const title = subview === 'orders' ? '订单' : subview === 'tasks' ? '待处理' : subview === 'reviews' ? '评价' : subview === 'coupons' ? '核销券' : tab === 'today' ? '今日' : tab === 'floor' ? '现场' : tab === 'team' ? '团队' : '经营';

  return <section className="manager-p0-page">
    <header className="manager-p0-head">
      <div>
        {subview ? <button type="button" className="manager-p0-back" onClick={() => setSubview(null)}><ArrowLeftOutlined /> 返回</button> : null}
        <h1>{title}</h1>
        <p>{subview ? '店长工作台' : tab === 'today' ? '今天最该做的事' : tab === 'floor' ? '沙发位只读 · 状态由系统生成' : tab === 'team' ? '学习、考核与总部抽检' : '照片、录音、评价和券'}</p>
      </div>
      <Button aria-label="刷新" icon={<ReloadOutlined />} loading={loading} onClick={() => { void load(true); if (tab === 'floor') setMapRefresh((value) => value + 1); }} />
    </header>

    {tab === 'today' && !subview && <ManagerTodayView daily={daily} team={team} workbench={workbench}
      onOpenFloor={() => openTab('floor')} onOpenOps={() => openTab('ops')} onOpenTeam={() => openTab('team')}
      onOpenReviews={() => setSubview('reviews')} onOpenCoupons={() => void generateCoupon()}
      onOpenOrders={() => { setOrdersRefresh((value) => value + 1); setSubview('orders'); }} onOpenTasks={() => setSubview('tasks')} />}
    {tab === 'floor' && !subview && <div className="manager-p0-stack">
      <section className="manager-p0-card">
        <div className="manager-p0-card-head"><div><small>今日巡检</small><h3>{daily?.completion.areas_done || 0}/5 区域</h3></div><Button size="small" onClick={() => openTab('ops')}>去拍照</Button></div>
        <div className="manager-p0-area-chips">{daily?.areas.map((area: { key: string; label: string; done: boolean }) => <span key={area.key} className={area.done ? 'done' : ''}>{area.done ? '✓ ' : ''}{area.label}</span>)}</div>
        <p className="manager-p0-muted">沙发位、房间、足疗床均为只读；店长不修改座位状态。</p>
      </section>
      <ManagerPositionView key={storeId} storeId={storeId} refreshKey={mapRefresh} />
    </div>}
    {tab === 'team' && !subview && <ManagerTeamView team={team} onRefresh={() => load(true)} />}
    {tab === 'ops' && !subview && <ManagerDailyOpsView daily={daily} loading={loading} onRefresh={() => load(true)} onOpenReviews={() => setSubview('reviews')} onOpenCoupons={() => void generateCoupon()} onOpenRedeemCoupon={() => { setCouponToken(''); setSubview('coupons'); }} />}

    {subview === 'orders' && <ManagerServiceOrdersView refreshKey={ordersRefresh} onOpenPositions={() => openTab('floor')} />}
    {subview === 'tasks' && <ManagerTasksView onOpenReviews={() => setSubview('reviews')} onOpenPositions={() => openTab('floor')} onOpenOrders={() => setSubview('orders')} />}
    {subview === 'reviews' && <ManagerReviewsView focus={reviewFocus} onFocusConsumed={() => setReviewFocus(null)} onChanged={() => void load(true)} onFocusError={() => message.error('评价链接已失效')} />}
    {subview === 'coupons' && <ManagerCouponRedeemView initialToken={couponToken} onBack={() => setSubview(null)} />}

    {couponShare && <Modal open title="半价券链接" footer={null} onCancel={() => setCouponShare(null)}>
      <div className="manager-p0-coupon-share"><p>发给顾客：不登录也能先看券和核销码，登录后自动存入券包。60 天有效。</p><p className="manager-p0-muted">本店已发 {couponShare.issued}/{couponShare.limit} 张，剩余 {couponShare.remaining} 张。</p>{couponShare.qr && <img src={couponShare.qr} alt="半价券领取二维码" />}<Input readOnly value={couponShare.link} /><div><Button onClick={() => void navigator.clipboard.writeText(couponShare.link).then(() => message.success('链接已复制')).catch(() => message.info(couponShare.link))}>复制链接</Button><Button type="primary" loading={couponBusy} onClick={() => void generateCoupon()}><GiftOutlined /> 重新生成链接</Button></div></div>
    </Modal>}

    <nav className="manager-p0-nav" aria-label="店长导航">
      {([['today', '今日', <HomeOutlined />], ['floor', '现场', <ShopOutlined />], ['team', '团队', <TeamOutlined />], ['ops', '经营', <AppstoreOutlined />]] as const).map(([key, label, icon]) => <button type="button" key={key} className={tab === key && !subview ? 'active' : ''} onClick={() => openTab(key)}>{icon}<span>{label}</span></button>)}
    </nav>
  </section>;
}

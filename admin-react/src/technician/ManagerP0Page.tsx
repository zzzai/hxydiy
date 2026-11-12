import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Input, Modal, message } from 'antd';
import { ArrowLeftOutlined, HomeOutlined, ReloadOutlined, ShopOutlined, GiftOutlined, UserOutlined } from '@ant-design/icons';
import QRCode from 'qrcode';
import { createHalfPriceCouponLink, getManagerDaily, getManagerTeam, getManagerWorkbench, getStaff } from '../api';
import { parseManagerReview, takeManagerPendingOrder, takeManagerPendingReview, type PendingReview } from '../wecomSession';
import { useTechnicianSession } from './useTechnicianSession';
import { isMobileManager } from './managerMobile';
import ManagerTodayHomeView from './ManagerTodayHomeView';
import ManagerDailyOpsView from './ManagerDailyOpsView';
import ManagerTeamView from './ManagerTeamView';
import ManagerPositionView from './ManagerPositionView';
import ManagerTasksView from './ManagerTasksView';
import ManagerServiceOrdersView from './ManagerServiceOrdersView';
import ManagerReviewsView from './ManagerReviewsView';
import ManagerCouponRedeemView from './ManagerCouponRedeemView';
import ManagerCouponHistoryView from './ManagerCouponHistoryView';
import './manager-mobile.css';
import './manager-p0.css';
import './manager-home.css';

type Tab = 'today' | 'floor' | 'coupons' | 'me';
type Subview = 'orders' | 'tasks' | 'reviews' | 'coupons' | 'coupon-history' | 'ops' | null;

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
  const title = subview === 'orders' ? '订单' : subview === 'tasks' ? '待处理' : subview === 'reviews' ? '评价' : subview === 'coupons' ? '核销券' : subview === 'coupon-history' ? '券记录' : subview === 'ops' ? '巡检与晨会' : '';

  return <section className="manager-p0-page">
    {subview ? <header className="manager-p0-head">
      <div>
        <button type="button" className="manager-p0-back" onClick={() => setSubview(null)}><ArrowLeftOutlined /> 返回</button>
        <h1>{title}</h1>
        <p>{subview === 'coupon-history' ? '发券、领取与核销记录' : subview === 'ops' ? '照片、晨会和今日留痕' : '店长工作台'}</p>
      </div>
      {subview !== 'coupon-history' && <Button aria-label="刷新" icon={<ReloadOutlined />} loading={loading} onClick={() => void load(true)} />}
    </header> : null}

    {tab === 'today' && !subview && <ManagerTodayHomeView daily={daily} workbench={workbench}
      onOpenOps={() => setSubview('ops')} onOpenTasks={() => setSubview('tasks')}
      onOpenCoupons={() => void generateCoupon()} onOpenRedeemCoupon={() => { setCouponToken(''); setSubview('coupons'); }}
      onOpenCouponHistory={() => setSubview('coupon-history')} />}

    {tab === 'floor' && !subview && <div className="manager-p0-stack">
      <div className="manager-home-lead"><p>现场 · 只读</p><h1>座位和房间</h1><span>座位状态由系统生成，店长不需要手动修改。</span></div>
      <ManagerPositionView key={storeId} storeId={storeId} refreshKey={0} />
    </div>}

    {tab === 'coupons' && !subview && <div className="manager-coupon-center">
      <div className="manager-home-lead"><p>本店 · 近 30 天</p><h1>券</h1><span>发券、核销和记录集中在这里。</span></div>
      <div className="manager-home-quick"><button type="button" onClick={() => void generateCoupon()}><b>券</b><span>发券</span></button><button type="button" onClick={() => { setCouponToken(''); setSubview('coupons'); }}><b>核</b><span>核销券</span></button><button type="button" onClick={() => setSubview('coupon-history')}><b>记</b><span>券记录</span></button></div>
      <ManagerCouponHistoryView />
    </div>}

    {tab === 'me' && !subview && <div className="manager-me-page">
      <div className="manager-home-lead"><p>店长</p><h1>我的</h1><span>{getStaff()?.name || '店长'} · {getStaff()?.store_name || '本店'}</span></div>
      <ManagerTeamView team={team} onRefresh={() => load(true)} />
    </div>}

    {subview === 'orders' && <ManagerServiceOrdersView refreshKey={ordersRefresh} onOpenPositions={() => openTab('floor')} />}
    {subview === 'tasks' && <ManagerTasksView onOpenReviews={() => setSubview('reviews')} onOpenPositions={() => openTab('floor')} onOpenOrders={() => setSubview('orders')} />}
    {subview === 'reviews' && <ManagerReviewsView focus={reviewFocus} onFocusConsumed={() => setReviewFocus(null)} onChanged={() => void load(true)} onFocusError={() => message.error('评价链接已失效')} />}
    {subview === 'ops' && <ManagerDailyOpsView daily={daily} loading={loading} onRefresh={() => load(true)} onOpenReviews={() => setSubview('reviews')} onOpenCoupons={() => void generateCoupon()} onOpenRedeemCoupon={() => { setCouponToken(''); setSubview('coupons'); }} onOpenCouponHistory={() => setSubview('coupon-history')} />}
    {subview === 'coupons' && <ManagerCouponRedeemView initialToken={couponToken} onBack={() => setSubview(null)} onOpenHistory={() => setSubview('coupon-history')} />}
    {subview === 'coupon-history' && <ManagerCouponHistoryView />}

    {couponShare && <Modal open title="半价券链接" footer={null} onCancel={() => setCouponShare(null)}>
      <div className="manager-p0-coupon-share"><p>发给顾客：不登录也能先看券和核销码，登录后自动存入券包。60 天有效。</p><p className="manager-p0-muted">本店已发 {couponShare.issued}/{couponShare.limit} 张，剩余 {couponShare.remaining} 张。</p>{couponShare.qr && <img src={couponShare.qr} alt="半价券领取二维码" />}<Input readOnly value={couponShare.link} /><div><Button onClick={() => void navigator.clipboard.writeText(couponShare.link).then(() => message.success('链接已复制')).catch(() => message.info(couponShare.link))}>复制链接</Button><Button type="primary" loading={couponBusy} onClick={() => void generateCoupon()}><GiftOutlined /> 重新生成链接</Button></div></div>
    </Modal>}

    <nav className="manager-p0-nav" aria-label="店长导航">
      {([['today', '今日', <HomeOutlined />], ['floor', '现场', <ShopOutlined />], ['coupons', '券', <GiftOutlined />], ['me', '我的', <UserOutlined />]] as const).map(([key, label, icon]) => <button type="button" key={key} className={tab === key && !subview ? 'active' : ''} onClick={() => openTab(key)}>{icon}<span>{label}</span></button>)}
    </nav>
  </section>;
}

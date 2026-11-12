import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Input, Modal, message } from 'antd';
import { ArrowLeftOutlined, DownloadOutlined, HomeOutlined, ReloadOutlined, ShopOutlined, GiftOutlined, UserOutlined } from '@ant-design/icons';
import { createHalfPriceCouponLink, getManagerDaily, getManagerTeam, getManagerWorkbench, getStaff } from '../api';
import { createCouponPoster } from './couponPoster';
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
  const [couponShare, setCouponShare] = useState<{ link: string; issued: number; remaining: number; limit: number } | null>(null);
  const [posterUrl, setPosterUrl] = useState('');
  const [posterBusy, setPosterBusy] = useState(false);
  const [posterError, setPosterError] = useState('');
  const [couponBusy, setCouponBusy] = useState(false);
  const [couponToken, setCouponToken] = useState('');
  const [reviewFocus, setReviewFocus] = useState<PendingReview | null>(null);
  const [ordersRefresh, setOrdersRefresh] = useState(0);
  const uiState = useRef({ tab, subview });
  uiState.current = { tab, subview };

  useEffect(() => {
    // WeCom swipe-back is a browser history move. Keep one manager entry in
    // front of the app so a swipe closes the current sheet/subview instead of
    // falling back to the WeCom login/verification page.
    const pushGuard = () => window.history.pushState({ ...(window.history.state || {}), hxyManagerGuard: true }, '', window.location.href);
    pushGuard();
    const onPop = () => {
      const current = uiState.current;
      if (current.subview) setSubview(null);
      else if (current.tab !== 'today') setTab('today');
      pushGuard();
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);
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
      setCouponShare({ link, issued: response.data.issued, remaining: response.data.remaining, limit: response.data.limit });
    } catch (failure) {
      const detail = (failure as { response?: { data?: { detail?: { message?: string } } } })?.response?.data?.detail;
      message.error(detail?.message || '生成券链接失败，请重试');
    } finally {
      setCouponBusy(false);
    }
  };

  useEffect(() => {
    if (!couponShare) {
      setPosterUrl('');
      setPosterError('');
      setPosterBusy(false);
      return undefined;
    }
    let active = true;
    let objectUrl = '';
    setPosterUrl('');
    setPosterError('');
    setPosterBusy(true);
    void createCouponPoster(couponShare.link, getStaff()?.store_name || '本店')
      .then((blob) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setPosterUrl(objectUrl);
      })
      .catch(() => { if (active) setPosterError('海报生成失败，请重新生成链接'); })
      .finally(() => { if (active) setPosterBusy(false); });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [couponShare]);

  const savePoster = () => {
    if (!posterUrl) return;
    const anchor = document.createElement('a');
    anchor.href = posterUrl;
    anchor.download = `荷小悦-半价券-${new Date().toISOString().slice(0, 10)}.png`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
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
      <div className="manager-home-lead"><p>本店 · 近 30 天</p><h1>券</h1></div>
      <div className="manager-coupon-segments" role="tablist" aria-label="券功能">
        <button type="button" role="tab" aria-selected="true" className="active">记录</button>
        <button type="button" role="tab" aria-selected="false" onClick={() => { setCouponToken(''); setSubview('coupons'); }}>核销</button>
        <button type="button" role="tab" aria-selected="false" onClick={() => void generateCoupon()}>发券</button>
      </div>
      <ManagerCouponHistoryView embedded />
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

    {couponShare && <Modal open title="半价券海报" footer={null} onCancel={() => setCouponShare(null)}>
      <div className="manager-p0-coupon-share">
        {posterBusy ? <div className="manager-coupon-poster-loading">正在生成海报…</div> : posterError ? <div className="manager-coupon-poster-error">{posterError}</div> : posterUrl ? <img className="manager-coupon-poster-image" src={posterUrl} alt="荷小悦半价券分享海报" /> : null}
        <p className="manager-p0-muted">保存海报后发给顾客；顾客扫码领取，登录后自动存入券包。</p>
        <p className="manager-p0-muted">本店已发 {couponShare.issued}/{couponShare.limit} 张，剩余 {couponShare.remaining} 张。</p>
        <Input readOnly value={couponShare.link} />
        <div><Button type="primary" icon={<DownloadOutlined />} disabled={!posterUrl || posterBusy} onClick={savePoster}>保存海报</Button><Button onClick={() => void navigator.clipboard.writeText(couponShare.link).then(() => message.success('链接已复制')).catch(() => message.info(couponShare.link))}>复制链接</Button><Button loading={couponBusy} onClick={() => void generateCoupon()}>重新生成</Button></div>
      </div>
    </Modal>}

    <nav className="manager-p0-nav" aria-label="店长导航">
      {([['today', '今日', <HomeOutlined />], ['floor', '现场', <ShopOutlined />], ['coupons', '券', <GiftOutlined />], ['me', '我的', <UserOutlined />]] as const).map(([key, label, icon]) => <button type="button" key={key} className={tab === key && !subview ? 'active' : ''} onClick={() => openTab(key)}>{icon}<span>{label}</span></button>)}
    </nav>
  </section>;
}

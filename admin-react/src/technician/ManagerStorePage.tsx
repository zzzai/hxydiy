import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, Drawer, Pagination, Spin, Tag, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { getManagerWorkbench, getSelectionSession, getSelectionSessions, getStaff } from '../api';
import { takeManagerPendingOrder, takeManagerPendingReview } from '../wecomSession';
import { selectionChangeItemSummary } from '../selectionChanges';
import { useTechnicianSession } from './useTechnicianSession';
import { MANAGER_PAGE_SIZE, isMobileManager, managerError, managerListParams, managerPrice, managerSourceLabel, managerWorkflowColor, managerWorkflowLabel, readManagerPage, readManagerSelection } from './managerMobile';
import type { ManagerSelection, ManagerSelectionItem } from './managerMobile';
import ManagerPositionView from './ManagerPositionView';
import ManagerReviewsView from './ManagerReviewsView';
import ManagerTasksView from './ManagerTasksView';
import './manager-mobile.css';

function timeText(value?: string) {
  if (!value || Number.isNaN(Date.parse(value))) return '时间待核实';
  return new Date(value).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
}

function ItemList({ items }: { items: ManagerSelectionItem[] }) {
  return <ul className="manager-item-list">{items.length ? items.map((item, index) => <li key={index}>{selectionChangeItemSummary(item)}</li>) : <li>未填写项目</li>}</ul>;
}

/**
 * 店长移动工作台只负责查看订单。
 * 顾客提交后由系统归单，店长不再需要逐单确认或真实分配座位。
 */
export default function ManagerStorePage() {
  const current = useTechnicianSession();
  const storeId = getStaff()?.store_id;
  const [view, setView] = useState<'tasks' | 'selections' | 'positions' | 'reviews'>('selections');
  const [mapRefresh, setMapRefresh] = useState(0);
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<ManagerSelection[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState('');
  const [forbidden, setForbidden] = useState(false);
  const [detail, setDetail] = useState<ManagerSelection | null>(null);
  const [workbench, setWorkbench] = useState<{ summary?: Record<string, number>; attention?: Array<{ key: string; label: string; count: number }> }>();
  const [reviewFocus, setReviewFocus] = useState<{ type: 'service_review'; id: number } | null>(null);
  const [deepLinkError, setDeepLinkError] = useState('');
  const [staleOnly, setStaleOnly] = useState(false);
  const [period, setPeriod] = useState<'all' | 'today' | '7d'>('all');
  const listVersion = useRef(0);
  const detailRef = useRef(detail);
  detailRef.current = detail;

  const load = useCallback(async (silent = false, force = false) => {
    if (!current() || !isMobileManager(getStaff())) return;
    const version = ++listVersion.current;
    if (!silent) setLoading(true);
    try {
      void getManagerWorkbench().then(response => { if (current()) setWorkbench(response.data); }).catch(() => undefined);
      const query = managerListParams('all', page);
      const response = await getSelectionSessions(query.status, query.needs_position_assignment, { page: query.page, page_size: query.page_size }, true, staleOnly, period);
      if (!current() || version !== listVersion.current) return;
      const data = readManagerPage(response.data, Number(storeId));
      const lastPage = Math.max(1, Math.ceil(data.total / MANAGER_PAGE_SIZE));
      if (page > lastPage) {
        setPage(lastPage);
        return;
      }
      setItems(data.items); setTotal(data.total); setListError(''); setForbidden(false);
    } catch (error) {
      if (!current() || version !== listVersion.current) return;
      const failure = managerError(error);
      setItems([]); setListError(failure.text);
      if (failure.forbidden) setForbidden(true);
    } finally {
      if (current() && version === listVersion.current) setLoading(false);
    }
  }, [current, page, storeId, staleOnly, period]);

  useEffect(() => { if (view === 'selections') void load(); return () => { ++listVersion.current; }; }, [load, view]);
  useEffect(() => {
    if (view !== 'selections') return;
    const refresh = () => {
      if (document.visibilityState !== 'visible' || detailRef.current) return;
      void load(true);
    };
    const timer = window.setInterval(refresh, 3000);
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [load, view]);
  useEffect(() => {
    if (!current() || !isMobileManager(getStaff()) || !storeId) return;
    setDeepLinkError('');
    const directReview = new URLSearchParams(window.location.search).get('review');
    const directReviewMatch = directReview?.match(/^service_review:([1-9][0-9]{0,17})$/);
    const review = directReviewMatch
      ? { type: 'service_review' as const, id: Number(directReviewMatch[1]) }
      : takeManagerPendingReview();
    if (review) {
      setDetail(null);
      setReviewFocus(review);
      setView('reviews');
      return;
    }
    const orderId = new URLSearchParams(window.location.search).get('order') || takeManagerPendingOrder();
    if (!orderId || !/^[A-Za-z0-9_-]{8,128}$/.test(orderId)) return;
    let cancelled = false;
    void getSelectionSession(orderId).then(response => {
      if (cancelled || !current()) return;
      try {
        setDetail(readManagerSelection(response.data, Number(storeId)));
      } catch {
        // Ignore malformed deep links; the normal workbench remains usable.
      }
    }).catch(() => { if (!cancelled) setDeepLinkError('订单链接已失效或无权查看，已返回门店列表。'); });
    return () => { cancelled = true; };
  }, [current, storeId]);

  const content = () => {
    if (listError) return <Alert type="error" showIcon message={listError} action={<Button onClick={() => void load()}>重试</Button>} />;
    if (loading && !items.length) return <div className="manager-empty"><Spin size="small" /><span>正在加载订单</span></div>;
    if (!items.length) return <div className="manager-empty"><strong>暂无订单</strong><span>顾客提交后会在这里显示</span></div>;
    return <div className="manager-selection-list">
      {items.map(item => {
        const price = managerPrice(item);
        return <button type="button" className="manager-selection-card" key={item.id} onClick={() => setDetail(item)}>
          <div className="manager-card-top">
            <span>{item.position?.name || (item.needs_position_assignment ? '现场安排' : '未安排座位')}</span>
            <Tag color={managerWorkflowColor(item)}>{managerWorkflowLabel(item)}</Tag>
          </div>
          <ItemList items={item.items} />
          <span className="manager-order-code">订单 · {item.id.slice(-8)}</span>
          <div className="manager-card-meta"><span>{item.customer?.nickname || '顾客'}{item.customer?.is_member ? ' · 会员' : ''}</span><span>{managerSourceLabel(item.source)}</span></div>
          <div className="manager-card-bottom"><time>{timeText(item.submitted_at || item.created_at)}</time><span>{price.label} <strong>{price.value}</strong></span></div>
        </button>;
      })}
    </div>;
  };

  return <section className="manager-store-page">
    <header className="manager-page-heading">
      <div>
        <h1>门店工作台</h1>
        <p>{view === 'tasks' ? '未分配、超时与评价跟进' : view === 'selections' ? '订单只读，确认与超时由系统处理' : view === 'positions' ? '按沙发、房间查看当前订单' : '查看本店评价并记录跟进'}</p>
      </div>
      <Button aria-label={view === 'tasks' ? '刷新待处理' : view === 'selections' ? '刷新门店订单' : view === 'positions' ? '刷新门店座位' : '刷新门店评价'} icon={<ReloadOutlined />} loading={view === 'selections' && loading} onClick={() => { if (view === 'positions') setMapRefresh(value => value + 1); else if (view === 'selections') void load(true, true); }} />
    </header>
    {deepLinkError && <Alert type="warning" showIcon closable message={deepLinkError} onClose={() => setDeepLinkError('')} />}
    <div className="manager-workbench-summary" aria-label="今日门店概览">
      <span><strong>{workbench?.summary?.today_orders ?? '—'}</strong>今日订单</span>
      <span><strong>{workbench?.summary?.waiting_service ?? '—'}</strong>待服务</span>
      <span><strong>{workbench?.summary?.in_service ?? '—'}</strong>服务中</span>
      <span><strong>{workbench?.summary?.completed_today ?? '—'}</strong>已完成</span>
      <button type="button" className={workbench?.summary?.attention ? 'has-attention' : ''} onClick={() => setView('tasks')}><strong>{workbench?.summary?.attention ?? '—'}</strong>需处理</button>
    </div>
    <nav className="manager-view-tabs" aria-label="工作台视图">
      <button type="button" aria-pressed={view === 'tasks'} onClick={() => { setDetail(null); setView('tasks'); }}>待处理</button>
      <button type="button" aria-pressed={view === 'selections'} onClick={() => { setDetail(null); setStaleOnly(false); setView('selections'); }}>订单</button>
      <button type="button" aria-pressed={view === 'positions'} onClick={() => { setDetail(null); setView('positions'); }}>座位</button>
      <button type="button" aria-pressed={view === 'reviews'} onClick={() => { setDetail(null); setView('reviews'); }}>评价</button>
    </nav>
    {forbidden && <Alert type="warning" message="当前账号不能查看门店订单，请联系管理员核对权限。" />}
    {view === 'tasks' ? <ManagerTasksView onOpenReviews={() => setView('reviews')} onOpenPositions={() => setView('positions')} onOpenOrders={() => { setStaleOnly(true); setPeriod('all'); setView('selections'); }} />
      : view === 'positions' ? <ManagerPositionView key={storeId} storeId={Number(storeId)} refreshKey={mapRefresh} />
      : view === 'reviews' ? <ManagerReviewsView focus={reviewFocus} onFocusConsumed={() => setReviewFocus(null)} onChanged={() => void load(true, true)} onFocusError={() => setDeepLinkError('评价链接已失效或无权查看，已返回评价列表。')} />
        : <>
      {!staleOnly && <div className="manager-order-period" role="group" aria-label="订单时间范围">
        {([['today', '今天'], ['7d', '近 7 天'], ['all', '全部']] as const).map(([value, label]) => <button key={value} type="button" aria-pressed={period === value} onClick={() => { setPage(1); setItems([]); setPeriod(value); }}>{label}</button>)}
      </div>}
      {staleOnly && <Alert type="warning" showIcon message="只显示超过 30 分钟仍未开始的订单" action={<Button size="small" onClick={() => setStaleOnly(false)}>查看全部订单</Button>} />}
      {content()}
      {!listError && total > 0 && <div className="manager-pagination"><span>共 {total} 份订单</span><Pagination simple current={page} pageSize={MANAGER_PAGE_SIZE} total={total} showSizeChanger={false} onChange={next => { setItems([]); setPage(next); setDetail(null); }} /></div>}
    </>}
    <Drawer title="订单详情" placement="bottom" height="min(90dvh, 760px)" rootClassName="manager-detail-drawer" open={Boolean(detail)} onClose={() => setDetail(null)} destroyOnClose footer={<div className="manager-detail-actions"><Button size="large" onClick={() => setDetail(null)}>关闭详情</Button><Button size="large" loading={loading} onClick={() => void load(true, true)}>刷新订单</Button></div>}>
      {detail && <>
        <div className="manager-detail-intro">
          <span>{detail.position?.name || (detail.needs_position_assignment ? '现场安排' : '未安排座位')}</span>
          <Tag color={managerWorkflowColor(detail)}>{managerWorkflowLabel(detail)}</Tag>
        </div>
        <span className="manager-order-code">订单 · {detail.id.slice(-8)}</span>
        <ItemList items={detail.items} />
        <div className="manager-detail-price"><span>{managerPrice(detail).label} <small>{managerPrice(detail).priceType}</small></span><strong>{managerPrice(detail).value}</strong></div>
        <dl className="manager-detail-meta">
          <div><dt>顾客</dt><dd>{detail.customer?.nickname || '顾客'}{detail.customer?.phone ? ' · ' + detail.customer.phone : ''}</dd></div>
          <div><dt>来源</dt><dd>{managerSourceLabel(detail.source)}</dd></div>
          <div><dt>提交时间</dt><dd>{timeText(detail.submitted_at || detail.created_at)}</dd></div>
        </dl>
        {Boolean(detail.timeline?.length) && <ol className="manager-order-timeline">{(detail.timeline || []).map(event => <li key={event.key}><span>{event.label}</span><time>{timeText(event.at)}</time></li>)}</ol>}
        {detail.feedback && <div className="manager-order-review"><div><Tag color={detail.feedback.rating <= 2 ? 'red' : 'gold'}>{detail.feedback.rating} 星</Tag><span>{detail.feedback.note || (detail.feedback.tags || []).join('、') || '顾客已评价'}</span></div><Button onClick={() => { setDetail(null); setReviewFocus({ type: 'service_review', id: detail.feedback!.id }); setView('reviews'); }}>查看评价详情</Button></div>}
        <p className="manager-detail-note">订单仅供查看；服务状态以技师确认/结束为准。</p>
        <Typography.Text type="secondary">如需取消或调整，请联系门店负责人。</Typography.Text>
      </>}
    </Drawer>
  </section>;
}

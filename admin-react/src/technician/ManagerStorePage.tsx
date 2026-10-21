import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, Drawer, Pagination, Spin, Tag, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { getSelectionSession, getSelectionSessions, getStaff } from '../api';
import { selectionChangeItemSummary } from '../selectionChanges';
import { useTechnicianSession } from './useTechnicianSession';
import { MANAGER_PAGE_SIZE, isMobileManager, managerError, managerListParams, managerOrderStatusLabel, managerPrice, managerSourceLabel, readManagerPage, readManagerSelection } from './managerMobile';
import type { ManagerSelection, ManagerSelectionItem } from './managerMobile';
import ManagerPositionView from './ManagerPositionView';
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
  const [view, setView] = useState<'selections' | 'positions'>('selections');
  const [mapRefresh, setMapRefresh] = useState(0);
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<ManagerSelection[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState('');
  const [forbidden, setForbidden] = useState(false);
  const [detail, setDetail] = useState<ManagerSelection | null>(null);
  const listVersion = useRef(0);
  const detailRef = useRef(detail);
  detailRef.current = detail;

  const load = useCallback(async (silent = false, force = false) => {
    if (!current() || !isMobileManager(getStaff())) return;
    const version = ++listVersion.current;
    if (!silent) setLoading(true);
    try {
      const query = managerListParams('all', page);
      const response = await getSelectionSessions(query.status, query.needs_position_assignment, { page: query.page, page_size: query.page_size }, true);
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
  }, [current, page, storeId]);

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
    const orderId = new URLSearchParams(window.location.search).get('order');
    if (!orderId || !/^[A-Za-z0-9_-]{8,128}$/.test(orderId)) return;
    let cancelled = false;
    void getSelectionSession(orderId).then(response => {
      if (cancelled || !current()) return;
      try {
        setDetail(readManagerSelection(response.data, Number(storeId)));
      } catch {
        // Ignore malformed deep links; the normal workbench remains usable.
      }
    }).catch(() => undefined);
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
            <Tag color={item.status === 'submitted' ? 'gold' : item.status === 'confirmed' ? 'green' : undefined}>{managerOrderStatusLabel(item.status)}</Tag>
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
        <p>{view === 'selections' ? '查看当前门店订单，无需逐单处理' : '按沙发、床位查看当前订单'}</p>
      </div>
      <Button aria-label={view === 'selections' ? '刷新门店订单' : '刷新门店座位'} icon={<ReloadOutlined />} loading={view === 'selections' && loading} onClick={() => { if (view === 'positions') setMapRefresh(value => value + 1); else void load(true, true); }} />
    </header>
    <nav className="manager-view-tabs" aria-label="工作台视图">
      <button type="button" aria-pressed={view === 'selections'} onClick={() => { setDetail(null); setView('selections'); }}>订单</button>
      <button type="button" aria-pressed={view === 'positions'} onClick={() => { setDetail(null); setView('positions'); }}>座位</button>
    </nav>
    {forbidden && <Alert type="warning" message="当前账号不能查看门店订单，请联系管理员核对权限。" />}
    {view === 'positions' ? <ManagerPositionView key={storeId} storeId={Number(storeId)} refreshKey={mapRefresh} /> : <>
      {content()}
      {!listError && total > 0 && <div className="manager-pagination"><span>共 {total} 份订单</span><Pagination simple current={page} pageSize={MANAGER_PAGE_SIZE} total={total} showSizeChanger={false} onChange={next => { setItems([]); setPage(next); setDetail(null); }} /></div>}
    </>}
    <Drawer title="订单详情" placement="bottom" height="min(90dvh, 760px)" rootClassName="manager-detail-drawer" open={Boolean(detail)} onClose={() => setDetail(null)} destroyOnClose footer={<div className="manager-detail-actions"><Button size="large" onClick={() => setDetail(null)}>关闭详情</Button><Button size="large" loading={loading} onClick={() => void load(true, true)}>刷新订单</Button></div>}>
      {detail && <>
        <div className="manager-detail-intro">
          <span>{detail.position?.name || (detail.needs_position_assignment ? '现场安排' : '未安排座位')}</span>
          <Tag>{managerOrderStatusLabel(detail.status)}</Tag>
        </div>
        <span className="manager-order-code">订单 · {detail.id.slice(-8)}</span>
        <ItemList items={detail.items} />
        <div className="manager-detail-price"><span>{managerPrice(detail).label} <small>{managerPrice(detail).priceType}</small></span><strong>{managerPrice(detail).value}</strong></div>
        <dl className="manager-detail-meta">
          <div><dt>顾客</dt><dd>{detail.customer?.nickname || '顾客'}{detail.customer?.phone ? ' · ' + detail.customer.phone : ''}</dd></div>
          <div><dt>来源</dt><dd>{managerSourceLabel(detail.source)}</dd></div>
          <div><dt>提交时间</dt><dd>{timeText(detail.submitted_at || detail.created_at)}</dd></div>
        </dl>
        <p className="manager-detail-note">订单仅供查看；无需店长确认或分配座位。</p>
        <Typography.Text type="secondary">如需取消或调整，请联系门店负责人。</Typography.Text>
      </>}
    </Drawer>
  </section>;
}

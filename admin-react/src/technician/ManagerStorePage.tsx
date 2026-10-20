import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Drawer, Input, Pagination, Select, Spin, Tag, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { approveSelectionChangeRequest, assignSelectionPosition, cancelSelectionSession, confirmSelectionSession, getLiveServicePositionMap, getSelectionChangeRequests, getSelectionSessions, getStaff, rejectSelectionChangeRequest } from '../api';
import { canApproveSelectionChange, selectionChangeItemSummary } from '../selectionChanges';
import { useTechnicianSession } from './useTechnicianSession';
import { MANAGER_FILTERS, MANAGER_PAGE_SIZE, createManagerActionRunner, isMobileManager, managerError, managerListParams, managerPrice, managerSelectionActions, managerSourceLabel, managerStatusLabel, readManagerPage } from './managerMobile';
import type { ManagerChange, ManagerFilter, ManagerSelection, ManagerSelectionItem } from './managerMobile';
import ManagerPositionView from './ManagerPositionView';
import './manager-mobile.css';

type Detail = { kind: 'selection'; item: ManagerSelection } | { kind: 'change'; item: ManagerChange };
type Action = 'view' | 'confirm' | 'cancel' | 'assign' | 'approve' | 'reject';
const actionLabels: Record<Action, string> = { view: '查看详情', confirm: '确认选单', cancel: '取消选单', assign: '安排座位', approve: '确认加选', reject: '拒绝加选' };
function timeText(value?: string) {
  if (!value || Number.isNaN(Date.parse(value))) return '时间待核实';
  return new Date(value).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
}
function ItemList({ items }: { items: ManagerSelectionItem[] }) {
  return <ul className="manager-item-list">{items.length ? items.map((item, index) => <li key={index}>{selectionChangeItemSummary(item)}</li>) : <li>未填写项目</li>}</ul>;
}
export default function ManagerStorePage() {
  const { message } = App.useApp();
  const current = useTechnicianSession();
  const storeId = getStaff()?.store_id;
  const [view, setView] = useState<'selections' | 'positions'>('selections');
  const [mapRefresh, setMapRefresh] = useState(0);
  const [filter, setFilter] = useState<ManagerFilter>('submitted');
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<ManagerSelection[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState('');
  const [changes, setChanges] = useState<ManagerChange[]>([]);
  const [changeError, setChangeError] = useState('');
  const [showAllChanges, setShowAllChanges] = useState(false);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [action, setAction] = useState<Action>('view');
  const [actionError, setActionError] = useState('');
  const [forbidden, setForbidden] = useState(false);
  const [busy, setBusy] = useState(false);
  const [roomId, setRoomId] = useState<number>();
  const [positions, setPositions] = useState<{ value: number; label: string }[]>([]);
  const [positionsLoading, setPositionsLoading] = useState(false);
  const [reason, setReason] = useState('');
  const listVersion = useRef(0);
  const changeVersion = useRef(0);
  const positionVersion = useRef(0);
  const listPending = useRef<{ key: string; version: number } | null>(null);
  const busyRef = useRef(false);
  const panelRef = useRef(detail);
  panelRef.current = detail;
  const runner = useRef(createManagerActionRunner()).current;

  const close = useCallback(() => {
    if (busyRef.current) return;
    ++positionVersion.current;
    setDetail(null); setAction('view'); setActionError(''); setReason(''); setRoomId(undefined); setPositions([]);
  }, []);
  const load = useCallback(async (silent = false, force = false) => {
    if (!current() || !isMobileManager(getStaff())) return;
    const queryKey = filter + ':' + page;
    if (!force && listPending.current?.key === queryKey) return;
    const version = ++listVersion.current;
    listPending.current = { key: queryKey, version };
    if (!silent) setLoading(true);
    try {
      const query = managerListParams(filter, page);
      const response = await getSelectionSessions(query.status, query.needs_position_assignment, { page: query.page, page_size: query.page_size });
      if (!current() || version !== listVersion.current) return;
      const data = readManagerPage(response.data, Number(storeId));
      const lastPage = Math.max(1, Math.ceil(data.total / MANAGER_PAGE_SIZE));
      if (page > lastPage) { setPage(lastPage); return; }
      setItems(data.items); setTotal(data.total); setListError('');
    } catch (error) {
      if (!current() || version !== listVersion.current) return;
      const failure = managerError(error);
      setItems([]); setListError(failure.text);
      if (failure.forbidden) setForbidden(true);
    } finally {
      if (listPending.current?.version === version) listPending.current = null;
      if (current() && version === listVersion.current) setLoading(false);
    }
  }, [current, filter, page, storeId]);
  const loadChanges = useCallback(async () => {
    if (!current() || !isMobileManager(getStaff())) return;
    const version = ++changeVersion.current;
    try {
      const response = await getSelectionChangeRequests();
      if (!current() || version !== changeVersion.current) return;
      if (!Array.isArray(response.data?.items)) throw new Error('加选请求暂不可用');
      setChanges(response.data.items); setChangeError('');
    } catch (error) {
      if (current() && version === changeVersion.current) {
        setChanges([]); setChangeError('加选请求加载失败，请刷新重试');
        if (managerError(error).forbidden) setForbidden(true);
      }
    }
  }, [current]);
  useEffect(() => { if (view === 'selections') void load(); return () => { ++listVersion.current; listPending.current = null; }; }, [load, view]);
  useEffect(() => { if (view === 'selections') void loadChanges(); return () => { ++changeVersion.current; }; }, [loadChanges, view]);
  useEffect(() => {
    if (view !== 'selections') return;
    const refresh = () => {
      if (document.visibilityState !== 'visible') { close(); return; }
      if (panelRef.current || busyRef.current) return;
      void load(true); void loadChanges();
    };
    const timer = window.setInterval(refresh, 3000);
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => { window.clearInterval(timer); window.removeEventListener('focus', refresh); document.removeEventListener('visibilitychange', refresh); };
  }, [load, loadChanges, close, view]);
  const open = (next: Detail) => {
    ++positionVersion.current;
    setDetail(next); setAction('view'); setActionError(''); setRoomId(undefined); setPositions([]); setReason('');
  };
  const loadPositions = async () => {
    const version = ++positionVersion.current;
    setPositionsLoading(true);
    try {
      const response = await getLiveServicePositionMap();
      if (!current() || version !== positionVersion.current) return;
      if (response.data.store_id !== storeId) throw new Error('当前门店服务位暂不可用');
      setPositions(response.data.positions.filter(position => position.state === 'available' && position.operational_status === 'active')
        .map(position => ({ value: position.id, label: position.customer_label || position.name })));
    } catch (error) {
      if (current() && version === positionVersion.current) {
        const failure = managerError(error);
        setActionError(failure.text);
        if (failure.forbidden) setForbidden(true);
      }
    } finally { if (current() && version === positionVersion.current) setPositionsLoading(false); }
  };
  const chooseAction = (next: Action) => {
    setAction(next); setActionError('');
    if (next === 'assign') void loadPositions();
  };
  const perform = async () => {
    if (!detail || action === 'view' || busyRef.current || forbidden || !current() || !isMobileManager(getStaff())) return;
    if (action === 'assign' && !roomId) { setActionError('请选择一个可用服务位'); return; }
    if (action === 'reject' && !reason.trim()) { setActionError('请填写拒绝原因'); return; }
    busyRef.current = true; setBusy(true); setActionError('');
    try {
      await runner.run(detail.kind + ':' + detail.item.id, async () => {
        if (detail.kind === 'selection') {
          if (action === 'confirm') return confirmSelectionSession(detail.item.id);
          if (action === 'cancel') return cancelSelectionSession(detail.item.id);
          if (action === 'assign') return assignSelectionPosition(detail.item.id, roomId!);
        } else {
          if (action === 'approve') return approveSelectionChangeRequest(detail.item.id);
          if (action === 'reject') return rejectSelectionChangeRequest(detail.item.id, reason.trim());
        }
        throw new Error('当前操作不可用');
      });
      if (!current()) return;
      message.success(({ confirm: '选单已确认', cancel: '选单已取消', assign: '座位已安排', approve: '加选已确认', reject: '加选已拒绝' } as Record<string, string>)[action]);
      setDetail(null); setAction('view'); setRoomId(undefined); setReason('');
      setMapRefresh(value => value + 1);
      await Promise.all([load(true, true), loadChanges()]);
    } catch (error) {
      if (!current()) return;
      const failure = managerError(error);
      setActionError(failure.text);
      if (failure.forbidden) setForbidden(true);
    } finally { busyRef.current = false; if (current()) setBusy(false); }
  };
  const selection = detail?.kind === 'selection' ? detail.item : null;
  const change = detail?.kind === 'change' ? detail.item : null;
  const actions = selection ? managerSelectionActions(selection) : null;
  const pendingChanges = changes.filter(item => canApproveSelectionChange(item.state));
  const displayedChanges = showAllChanges ? pendingChanges : pendingChanges.slice(0, 3);
  const relatedSelection = change ? items.find(item => item.id === change.selection.id) : undefined;
  const emptyText = filter === 'submitted' ? '暂无待确认选单' : filter === 'unassigned' ? '暂无待配位选单' : filter === 'confirmed' ? '暂无已确认选单' : '暂无选单';

  return <section className="manager-store-page">
    <header className="manager-page-heading"><div><h1>门店工作台</h1><p>{view === 'selections' ? '处理选单与顾客加选' : '按沙发、床位查看当前选单'}</p></div><Button aria-label={view === 'selections' ? '刷新门店选单' : '刷新门店座位'} icon={<ReloadOutlined />} loading={view === 'selections' && loading} onClick={() => { if (view === 'positions') setMapRefresh(value => value + 1); else { void load(); void loadChanges(); } }} /></header>
    <nav className="manager-view-tabs" aria-label="工作台视图"><button type="button" aria-pressed={view === 'selections'} disabled={busy} onClick={() => { close(); setView('selections'); }}>选单</button><button type="button" aria-pressed={view === 'positions'} disabled={busy} onClick={() => { close(); setView('positions'); }}>座位</button></nav>
    {view === 'positions' ? <ManagerPositionView key={storeId} storeId={Number(storeId)} refreshKey={mapRefresh} /> : <>
    {changeError && <Alert type="warning" message={changeError} />}
    {pendingChanges.length > 0 && <section className="manager-changes" aria-label="待确认加选">
      <div className="manager-section-heading"><h2>待确认加选 <span>{pendingChanges.length}</span></h2>{pendingChanges.length > 3 && <Button type="text" size="small" onClick={() => setShowAllChanges(!showAllChanges)}>{showAllChanges ? '收起' : '查看全部'}</Button>}</div>
      {displayedChanges.map(item => <button type="button" className="manager-change-row" key={item.id} onClick={() => open({ kind: 'change', item })}><span><strong>原选单 · {item.selection.id.slice(-8)}</strong><span>{item.revision.added_items.map(selectionChangeItemSummary).join('、') || '查看加选项目'}</span></span><span>处理</span></button>)}
    </section>}
    <nav className="manager-filter-row" aria-label="选单状态">{MANAGER_FILTERS.map(option => <button type="button" key={option.value} aria-pressed={filter === option.value} onClick={() => { if (filter !== option.value) { setItems([]); setTotal(0); setFilter(option.value); setPage(1); close(); } }}>{option.label}</button>)}</nav>
    {listError && <Alert type="error" showIcon message={listError} action={<Button onClick={() => void load()}>重试</Button>} />}
    {forbidden && <Alert type="warning" message="当前账号不能执行这些操作，请联系管理员核对权限。" />}
    {loading && !items.length ? <div className="manager-empty"><Spin size="small" /><span>正在加载选单</span></div> : !listError && !items.length ? <div className="manager-empty"><strong>{emptyText}</strong><span>顾客提交后会在这里显示</span></div> : <div className="manager-selection-list">
      {items.map(item => {
        const price = managerPrice(item);
        return <button type="button" className="manager-selection-card" key={item.id} onClick={() => open({ kind: 'selection', item })}>
          <div className="manager-card-top"><span>{item.position?.name || (item.needs_position_assignment ? '待安排座位' : '未安排座位')}</span><Tag color={item.status === 'submitted' ? 'gold' : item.status === 'confirmed' ? 'green' : undefined}>{managerStatusLabel(item.status)}</Tag></div>
          <ItemList items={item.items} /><span className="manager-order-code">选单 · {item.id.slice(-8)}</span>
          <div className="manager-card-meta"><span>{item.customer?.nickname || '顾客'}{item.customer?.is_member ? ' · 会员' : ''}</span><span>{managerSourceLabel(item.source)}</span></div>
          <div className="manager-card-bottom"><time>{timeText(item.submitted_at || item.created_at)}</time><span>{price.label} <strong>{price.value}</strong></span></div>
        </button>;
      })}
    </div>}
    {!listError && total > 0 && <div className="manager-pagination"><span>共 {total} 份选单</span><Pagination simple current={page} pageSize={MANAGER_PAGE_SIZE} total={total} showSizeChanger={false} onChange={next => { setItems([]); setPage(next); close(); }} /></div>}
    </>}
    <Drawer title={action !== 'view' ? actionLabels[action] : change ? '加选详情' : '选单详情'} placement="bottom" height="min(90dvh, 760px)" rootClassName="manager-detail-drawer" open={Boolean(detail)} onClose={close} maskClosable={!busy} closable={!busy} destroyOnClose footer={detail && <div className="manager-detail-actions">
      {action === 'view' ? <>
        {actions?.assign && <Button size="large" disabled={forbidden} onClick={() => chooseAction('assign')}>安排座位</Button>}
        {actions?.cancel && <Button size="large" danger disabled={forbidden} onClick={() => chooseAction('cancel')}>取消选单</Button>}
        {actions?.confirm && <Button size="large" type="primary" disabled={forbidden} onClick={() => chooseAction('confirm')}>确认选单</Button>}
        {change && canApproveSelectionChange(change.state) && <><Button size="large" danger disabled={forbidden} onClick={() => chooseAction('reject')}>拒绝加选</Button><Button size="large" type="primary" disabled={forbidden} onClick={() => chooseAction('approve')}>确认加选</Button></>}
      </> : <><Button size="large" disabled={busy} onClick={() => { setAction('view'); setActionError(''); }}>返回详情</Button><Button size="large" type="primary" danger={action === 'cancel' || action === 'reject'} loading={busy} disabled={forbidden || (action === 'assign' && (!roomId || positionsLoading))} onClick={() => void perform()}>{actionLabels[action]}</Button></>}
    </div>}>
      {selection && <><div className="manager-detail-intro"><span>{selection.position?.name || '未安排座位'}</span><Tag>{managerStatusLabel(selection.status)}</Tag></div><span className="manager-order-code">选单 · {selection.id.slice(-8)}</span><ItemList items={selection.items} /><div className="manager-detail-price"><span>{managerPrice(selection).label} <small>{managerPrice(selection).priceType}</small></span><strong>{managerPrice(selection).value}</strong></div>
        <dl className="manager-detail-meta"><div><dt>顾客</dt><dd>{selection.customer?.nickname || '顾客'}{selection.customer?.phone ? ' · ' + selection.customer.phone : ''}</dd></div><div><dt>来源</dt><dd>{managerSourceLabel(selection.source)}</dd></div><div><dt>提交时间</dt><dd>{timeText(selection.submitted_at || selection.created_at)}</dd></div></dl></>}
      {change && <><div className="manager-change-identity"><span>原选单</span><Typography.Paragraph copyable={{ text: change.selection.id }}>选单 · {change.selection.id.slice(-8)}</Typography.Paragraph><p>{relatedSelection ? [relatedSelection.position?.name || '未安排座位', relatedSelection.customer?.nickname || '顾客'].join(' · ') : '对应顾客与服务位信息未加载，请先核对原选单。'}</p></div><ItemList items={change.revision.added_items} /><p className="manager-detail-note">本次为服务中加选，请核对新增项目后处理。</p><dl className="manager-detail-meta"><div><dt>来源</dt><dd>{managerSourceLabel(change.selection.source)}</dd></div><div><dt>提交时间</dt><dd>{timeText(change.created_at)}</dd></div></dl></>}
      {action === 'confirm' && <p className="manager-action-explanation">确认接收以上项目，按顾客需求继续安排服务。</p>}
      {action === 'cancel' && <Alert type="warning" message="取消这份选单？" description="取消后不再进入门店处理队列，请先与顾客确认。" />}
      {action === 'approve' && <p className="manager-action-explanation">确认后，加选项目将加入本次服务。</p>}
      {action === 'reject' && <label className="manager-action-form">拒绝原因<Input.TextArea aria-label="拒绝原因" value={reason} onChange={event => setReason(event.target.value)} maxLength={256} rows={3} placeholder="说明本次不能加选的原因" disabled={busy} /></label>}
      {action === 'assign' && <div className="manager-action-form"><label htmlFor="manager-position">安排服务位</label><Select id="manager-position" aria-label="安排服务位" value={roomId} options={positions} loading={positionsLoading} disabled={busy} placeholder="选择可用的沙发或房间" onChange={setRoomId} size="large" style={{ width: '100%' }} getPopupContainer={node => node.parentElement!} /><p>只安排座位，不代表服务已经开始。</p>{!positionsLoading && !positions.length && <span>暂时没有可用服务位</span>}<Button type="link" disabled={busy} onClick={() => void loadPositions()}>刷新可用服务位</Button></div>}
      {actionError && <Alert type="error" showIcon message={actionError} />}
    </Drawer>
  </section>;
}

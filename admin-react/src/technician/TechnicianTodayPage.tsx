import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Drawer, Empty, List, Spin, Tag, Typography } from 'antd';
import { CheckCircleOutlined, EyeOutlined, PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { confirmTechnicianService, finishTechnicianService, getTechnicianMe, getTechnicianTasks } from '../api';
import {
  createTechnicianActionRunner,
  technicianBoardGroups,
  technicianOrderItemLabel,
  technicianPositionTone,
  technicianPriceLabel,
  technicianPriceLineValue,
  technicianPriceMode,
  technicianPriceModeLabel,
  technicianPriceTotalValue,
  technicianPricingLines,
  technicianPricingSummary,
  technicianStatusLabel,
} from './technicianMobile';
import TechnicianProfileSheet from './TechnicianProfileSheet';
import TechnicianServiceReferenceDrawer from './TechnicianServiceReferenceDrawer';

function orderSummary(order: any): string {
  return (order.items || []).map(technicianOrderItemLabel).filter(Boolean).join('、') || '顾客暂未填写项目';
}

function orderStatusLabel(status: string): string {
  return ({
    draft: '待处理',
    waiting_assignment: '待安排座位',
    assigned: '已派单',
    ready: '待服务',
    in_service: '服务中',
    pending_checkout: '待结账',
    completed: '已完成',
    cancelled: '已取消',
  } as Record<string, string>)[status] || '处理中';
}

function statusColor(status: string): string {
  return ({ draft: 'default', waiting_assignment: 'gold', assigned: 'gold', ready: 'blue', in_service: 'green', pending_checkout: 'cyan', completed: 'blue', cancelled: 'default' } as Record<string, string>)[status] || 'default';
}

function positionTagColor(status: string): string {
  return ({ available: 'green', held: 'gold', waiting_service: 'gold', in_service: 'cyan', post_service_present: 'blue', conflict: 'red', cleaning: 'purple', released: 'default', unavailable: 'default' } as Record<string, string>)[status] || 'default';
}

function taskToOrder(task: any): any {
  const occupancyStatus = task.occupancy_status;
  const status = task.conflict ? 'conflict'
    : task.unassigned || occupancyStatus === 'unassigned' ? 'waiting_assignment'
    : occupancyStatus === 'waiting_service' ? 'ready'
    : occupancyStatus === 'post_service_present' ? 'completed'
      : occupancyStatus === 'in_service' ? 'in_service' : 'cancelled';
  return {
    ...task,
    id: task.occupancy_id ?? null,
    status,
    customer: task.customer || (task.user_id ? { id: task.user_id, nickname: '顾客', phone_masked: '' } : null),
  };
}

function orderPriceSummary(pricing: any): string {
  return technicianPricingSummary(pricing);
}

function OrderItems({ order }: { order: any }) {
  const mode = technicianPriceMode(order.pricing);
  const priced = technicianPricingLines(order.pricing);
  const items = priced.length ? priced.map((line: any, index: number) => {
    const original = (order.items || []).find((item: any, itemIndex: number) => Number(item.line_index ?? itemIndex) === Number(line.line_index ?? index))
      || (order.items || [])[index];
    return { ...original, ...line, name: line.name || original?.name, diy_preferences: original?.diy_preferences };
  }) : (order.items || []);
  return <List
    header="服务项目"
    dataSource={items}
    locale={{ emptyText: '当前暂无服务项目' }}
    renderItem={(item: any) => {
      const { amount_cents, pending_label } = technicianPriceLineValue(mode, item);
      return <List.Item className="technician-order-item">
        <span className="technician-order-item-name">{technicianOrderItemLabel(item)}</span>
        <span className="technician-order-item-tail">
          {amount_cents != null && <span className="technician-order-line-price">
            <span>{technicianPriceModeLabel(mode)} {technicianPriceLabel(amount_cents)}</span>
          </span>}
          {amount_cents == null && pending_label && <span className="technician-order-line-pending">{pending_label}</span>}
          <span>×{item.quantity || 1}</span>
        </span>
      </List.Item>;
    }}
  />;
}

function OrderPricingBlock({ pricing }: { pricing: any }) {
  if (!pricing) return null;
  const mode = technicianPriceMode(pricing);
  const label = technicianPriceModeLabel(mode);
  const total = technicianPriceTotalValue(mode, pricing);
  return <section className="technician-order-pricing" aria-label="订单价格">
    <div className="technician-order-pricing-head">
      <span>本单价格</span>
      <span>{label}</span>
    </div>
    {mode !== 'unknown' && <div className="technician-order-pricing-pair">
      <div><span>{label}合计</span><strong>{total.pending_label ? '待确认' : technicianPriceLabel(total.amount_cents)}</strong></div>
    </div>}
    {mode === 'unknown' && <p className="technician-order-pricing-hint">价格类型待确认，暂不展示单价与合计</p>}
    {total.pending_label && <p className="technician-order-pricing-hint">{total.pending_label}</p>}
  </section>;
}

export default function TechnicianTodayPage() {
  const { message } = App.useApp();
  const [me, setMe] = useState<any>();
  const [tasks, setTasks] = useState<any[]>([]);
  const [unassignedTasks, setUnassignedTasks] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<number | null>(null);
  const [selectedOrder, setSelectedOrder] = useState<any>();
  const [profileOrder, setProfileOrder] = useState<any>();
  const [error, setError] = useState('');
  const activeLoads = useRef(0);
  const latestLoadRequest = useRef(0);
  const actionRunner = useRef(createTechnicianActionRunner()).current;

  const load = useCallback(async ({ background = false }: { background?: boolean } = {}) => {
    if (background && activeLoads.current > 0) return;
    const requestId = ++latestLoadRequest.current;
    activeLoads.current += 1;
    if (!background) setLoading(true);
    if (!background) setError('');
    try {
          const [profile, list] = await Promise.all([getTechnicianMe(), getTechnicianTasks()]);
          if (requestId !== latestLoadRequest.current) return;
          setMe(profile.data);
          setTasks(list.data?.items || []);
          setUnassignedTasks(list.data?.unassigned_items || []);
          setError('');
    } catch {
      if (requestId === latestLoadRequest.current && !background) setError('任务加载失败，请检查网络后重试');
    } finally {
      activeLoads.current -= 1;
      if (requestId === latestLoadRequest.current && !background) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const refresh = () => {
      if (document.visibilityState !== 'visible') return;
      void load({ background: true });
    };
    const refreshTimer = window.setInterval(refresh, 3000);
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') refresh();
    };
    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('focus', refresh);
    return () => {
      window.clearInterval(refreshTimer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('focus', refresh);
    };
  }, [load]);

  const act = async (order: any, action: 'confirm' | 'finish') => {
    const occupancyId = typeof order.occupancy_id === 'number' ? order.occupancy_id : null;
    if (!occupancyId) return;
    if (actionRunner.isRunning(action, occupancyId)) return;
    setActing(occupancyId);
    try {
      await actionRunner.run(action, occupancyId, (id, key) => action === 'confirm'
        ? confirmTechnicianService(id, key)
        : finishTechnicianService(id, key));
      message.success(action === 'confirm' ? '服务已开始' : '服务已结束，请填写服务记录');
      if (action === 'finish' && order.customer?.id && order.selection_session_id) {
        setProfileOrder({ ...order, status: 'completed', completed_by_me: true });
      }
      setSelectedOrder(undefined);
      await load();
    } catch {
      // API 拦截器负责展示服务端错误。
    } finally {
      setActing(null);
    }
  };

  const selectedOccupancyId = selectedOrder && typeof selectedOrder.occupancy_id === 'number' ? selectedOrder.occupancy_id : null;
  const selectedActions = selectedOccupancyId
    ? (selectedOrder.status === 'in_service' ? ['finish'] : selectedOrder.status === 'ready' ? ['confirm'] : [])
    : [];

  const groups = technicianBoardGroups(tasks);
  const boardCounts = tasks.reduce((counts, task) => {
    if (task.conflict) {
      counts.conflict += Number(task.conflict_count || 1);
      return counts;
    }
    if (!task.occupancy_id) return counts;
    if (task.occupancy_status === 'in_service') counts.inService += 1;
    else if (task.occupancy_status === 'waiting_service') counts.waiting += 1;
    else if (task.occupancy_status === 'post_service_present') counts.completed += 1;
    return counts;
  }, { waiting: 0, inService: 0, completed: 0, conflict: 0 });
  const boardSummary = [
    boardCounts.inService ? `服务中 ${boardCounts.inService} 单` : '',
    boardCounts.waiting ? `待服务 ${boardCounts.waiting} 单` : '',
    boardCounts.conflict ? `待核对 ${boardCounts.conflict} 项` : '',
    boardCounts.completed ? `已完成 ${boardCounts.completed} 单` : '',
  ].filter(Boolean).join(' · ');

  if (loading && !tasks.length && !unassignedTasks.length) return <div className="technician-loading"><Spin size="large" /></div>;

  return <div className="technician-today-page">
    <div className="technician-page-title">
      <div>
        <span className="technician-eyebrow">{new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })}</span>
        <h1>服务看板</h1>
            <p>{me?.technician?.name || '技师'} · {boardSummary || '当前没有待处理服务'} · 共 {tasks.length} 个服务位{unassignedTasks.length ? ` · 未排座 ${unassignedTasks.length} 单` : ''}</p>
      </div>
      <Button shape="circle" aria-label="刷新服务看板" icon={<ReloadOutlined />} onClick={() => void load()} loading={loading} />
    </div>
    {error && <Alert type="error" showIcon message={error} action={<Button size="small" onClick={() => void load()}>重试</Button>} />}
    {unassignedTasks.length > 0 && <section className="technician-board-section">
      <div className="technician-section-heading"><h2>未排座</h2><span>{unassignedTasks.length} 单</span></div>
      <div className="technician-unassigned-list">
        {unassignedTasks.map((task: any) => {
          const order = taskToOrder(task);
          const items = task.items || [];
          const itemCount = items.reduce((total: number, item: any) => total + Math.max(1, Number(item.quantity) || 1), 0);
          const submittedAt = task.submitted_at
            ? new Date(task.submitted_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
            : '--:--';
          return <button type="button" className="technician-unassigned-row" key={task.selection_session_id} onClick={() => setSelectedOrder(order)} aria-label={`查看${submittedAt}提交的未排座订单`}>
            <div className="technician-unassigned-row-head"><span className="technician-unassigned-time">{submittedAt}</span><span className="technician-unassigned-tag">未排座</span></div>
            <div className="technician-unassigned-summary">{orderSummary(order)}</div>
            <div className="technician-unassigned-count">{itemCount} 个项目</div>
            {task.pricing && <div className="technician-unassigned-price">{orderPriceSummary(task.pricing)}</div>}
          </button>;
        })}
      </div>
    </section>}
    {!tasks.length && !unassignedTasks.length && !error ? <div className="technician-empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前门店暂无服务位" /></div> : tasks.length > 0 && <section className="technician-board-section">
      <div className="technician-section-heading"><h2>服务位</h2><span>共 {tasks.length} 个</span></div>
      {groups.map((group) => <section className="technician-position-group" key={group.key}>
        <div className="technician-section-heading"><h3>{group.label}</h3><span>{group.items.length} 个</span></div>
        <div className="technician-position-grid">
          {group.items.map((task: any) => {
            const order = taskToOrder(task);
            const status = task.occupancy_status || 'available';
            const hasConflict = Boolean(task.conflict);
            const hasOrder = Boolean(task.occupancy_id && task.user_id) && !hasConflict;
            const tileStatus = hasConflict ? 'conflict' : status;
            return <button type="button" className={`technician-position-tile tone-${technicianPositionTone(tileStatus)}`} key={task.room_id} onClick={() => setSelectedOrder(order)} aria-label={`查看${task.room_name || '服务位'}${hasConflict ? '待核对状态' : hasOrder ? '订单' : '状态'}`}>
              <div className="technician-position-tile-top"><strong>{task.room_name || '服务位'}</strong><Tag color={positionTagColor(status)}>{technicianStatusLabel(status)}</Tag></div>
              <div className="technician-position-tile-body"><span className="technician-position-count">{hasConflict ? task.conflict_count : hasOrder ? ((task.items || []).length || 0) : '—'}</span><span>{hasConflict ? '条占用待核对' : hasOrder ? '个项目' : '暂无订单'}</span></div>
              <div className="technician-position-tile-summary">{hasConflict ? '同一房间存在多个活动占用，暂不可操作' : hasOrder ? orderSummary(order) : status === 'available' ? '空闲，可接待顾客' : '当前无可查看选单'}</div>
              {hasOrder && task.pricing && <div className="technician-position-tile-price">{orderPriceSummary(task.pricing)}</div>}
              <div className="technician-position-tile-action"><EyeOutlined /> {hasConflict ? '查看核对提示' : hasOrder ? '查看顾客订单' : '查看区位状态'}</div>
            </button>;
          })}
        </div>
      </section>)}
    </section>}
    <Drawer title={selectedOrder ? (selectedOrder.conflict ? `${selectedOrder.room_name || '服务位'}待核对` : selectedOrder.status === 'waiting_assignment' ? '未排座' : '顾客服务单') : '顾客服务单'} placement="bottom" height="min(78vh, 620px)" open={!!selectedOrder} onClose={() => setSelectedOrder(undefined)}>
      {selectedOrder && <div className="technician-order-drawer">
        {selectedOrder.conflict ? <Alert type="warning" showIcon message="服务位记录待核对" description={`该房间存在 ${selectedOrder.conflict_count || 2} 条活动占用记录。为避免误操作，当前不展示顾客选单，也不能确认或结束服务；请联系店长核对现场服务位。`} /> : selectedOrder.status === 'waiting_assignment' ? <>
        <div className="technician-order-drawer-head"><div><span className="technician-eyebrow">未排座</span><h2>未排座</h2></div><Tag>未排座</Tag></div>
        <Typography.Paragraph type="secondary">{selectedOrder.submitted_at ? new Date(selectedOrder.submitted_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false }) : '刚刚'} 提交</Typography.Paragraph>
        <OrderItems order={selectedOrder} />
        <OrderPricingBlock pricing={selectedOrder.pricing} />
        <Typography.Paragraph type="secondary">座位由前台安排。安排后会出现在对应沙发或房间。</Typography.Paragraph>
        </> : <>
        <div className="technician-order-drawer-head"><div><span className="technician-eyebrow">本次服务</span><h2>{selectedOrder.room_name || '服务位'}</h2></div><Tag color={statusColor(selectedOrder.status)}>{orderStatusLabel(selectedOrder.status)}</Tag></div>
        <Typography.Paragraph type="secondary">{selectedOrder.customer?.nickname || '顾客'} {selectedOrder.customer?.phone_masked || ''}</Typography.Paragraph>
        <OrderItems order={selectedOrder} />
        <OrderPricingBlock pricing={selectedOrder.pricing} />
        {selectedActions.length > 0 && selectedOrder.customer?.id && <TechnicianServiceReferenceDrawer inline occupancyId={selectedOccupancyId} open onClose={()=>{}} />}
        <div className="technician-task-card-foot">
          {selectedActions.includes('confirm') && <Button type="primary" block size="large" icon={<PlayCircleOutlined />} loading={acting === selectedOccupancyId} onClick={() => void act(selectedOrder, 'confirm')}>开始服务</Button>}
          {selectedActions.includes('finish') && <Button type="primary" block size="large" icon={<CheckCircleOutlined />} loading={acting === selectedOccupancyId} onClick={() => void act(selectedOrder, 'finish')}>服务结束</Button>}
          {selectedOccupancyId === null && <Typography.Text type="secondary">当前服务单接口未提供服务位占用凭证，仅支持查看。</Typography.Text>}
          {selectedOrder.completed_by_me && selectedOrder.customer?.id && selectedOrder.selection_session_id && <Button block size="large" onClick={() => { setProfileOrder(selectedOrder); setSelectedOrder(undefined); }}>填写服务参考</Button>}
          {selectedOrder.status === 'completed' && <Typography.Text type="secondary">服务记录完成后，服务位由前台按离店流程释放。</Typography.Text>}
        </div>
        </>}
      </div>}
    </Drawer>
    <TechnicianProfileSheet task={profileOrder} onClose={() => setProfileOrder(undefined)} onSaved={() => { setProfileOrder(undefined); void load(); }} />
  </div>;
}

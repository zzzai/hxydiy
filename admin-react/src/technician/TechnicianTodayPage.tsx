import { useCallback, useEffect, useState } from 'react';
import { Alert, App, Button, Drawer, Empty, List, Spin, Tag, Typography } from 'antd';
import { CheckCircleOutlined, EyeOutlined, PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { confirmTechnicianService, finishTechnicianService, getTechnicianMe, getTechnicianTasks } from '../api';
import {
  createTechnicianIdempotencyKey,
  technicianBoardGroups,
  technicianOrderItemLabel,
  technicianPositionTone,
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
    waiting_assignment: '待派单',
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
    : occupancyStatus === 'waiting_service' ? 'ready'
    : occupancyStatus === 'post_service_present' ? 'completed'
      : occupancyStatus === 'in_service' ? 'in_service' : 'cancelled';
  return {
    ...task,
    id: task.occupancy_id ?? `position-${task.room_id}`,
    status,
    customer: task.user_id ? { id: task.user_id, nickname: '顾客', phone_masked: '' } : null,
  };
}

export default function TechnicianTodayPage() {
  const { message } = App.useApp();
  const [me, setMe] = useState<any>();
  const [tasks, setTasks] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<number | null>(null);
  const [selectedOrder, setSelectedOrder] = useState<any>();
  const [profileOrder, setProfileOrder] = useState<any>();
  const [referenceOccupancyId, setReferenceOccupancyId] = useState<number | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async ({ background = false }: { background?: boolean } = {}) => {
    if (!background) setLoading(true);
    if (!background) setError('');
    try {
          const [profile, list] = await Promise.all([getTechnicianMe(), getTechnicianTasks()]);
          setMe(profile.data);
          setTasks(list.data?.items || []);
          setError('');
    } catch {
      if (!background) setError('任务加载失败，请检查网络后重试');
    } finally {
      if (!background) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const refresh = () => { void load({ background: true }); };
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
    setActing(occupancyId);
    try {
      const key = createTechnicianIdempotencyKey(action, occupancyId);
      if (action === 'confirm') await confirmTechnicianService(occupancyId, key);
      else await finishTechnicianService(occupancyId, key);
      message.success(action === 'confirm' ? '已确认服务' : '服务已结束');
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
  const activeOrderCount = tasks.reduce((total, task) => total + (task.conflict ? Number(task.conflict_count || 1) : (task.occupancy_id ? 1 : 0)), 0);

  if (loading && !tasks.length) return <div className="technician-loading"><Spin size="large" /></div>;

  return <div className="technician-today-page">
    <div className="technician-page-title">
      <div>
        <span className="technician-eyebrow">{new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })}</span>
        <h1>服务看板</h1>
            <p>{me?.technician?.name || '技师'} · {activeOrderCount ? `当前 ${activeOrderCount} 个服务单` : '当前没有顾客订单'} · 共 {tasks.length} 个服务位</p>
      </div>
      <Button shape="circle" aria-label="刷新服务看板" icon={<ReloadOutlined />} onClick={() => void load()} loading={loading} />
    </div>
    {error && <Alert type="error" showIcon message={error} action={<Button size="small" onClick={() => void load()}>重试</Button>} />}
    {!tasks.length && !error ? <div className="technician-empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前门店暂无服务位" /></div> : <section className="technician-board-section">
      <div className="technician-section-heading"><h2>服务位</h2><span>{activeOrderCount} 个订单</span></div>
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
              <div className="technician-position-tile-action"><EyeOutlined /> {hasConflict ? '查看核对提示' : hasOrder ? '查看顾客订单' : '查看区位状态'}</div>
            </button>;
          })}
        </div>
      </section>)}
    </section>}
    <Drawer title={selectedOrder ? (selectedOrder.conflict ? `${selectedOrder.room_name || '服务位'}待核对` : `服务单 #${selectedOrder.id}`) : '服务单'} placement="bottom" height="min(78vh, 620px)" open={!!selectedOrder} onClose={() => setSelectedOrder(undefined)}>
      {selectedOrder && <div className="technician-order-drawer">
        {selectedOrder.conflict ? <Alert type="warning" showIcon message="服务位记录待核对" description={`该房间存在 ${selectedOrder.conflict_count || 2} 条活动占用记录。为避免误操作，当前不展示顾客选单，也不能确认或结束服务；请联系店长核对现场服务位。`} /> : <>
        <div className="technician-order-drawer-head"><div><span className="technician-eyebrow">顾客服务单</span><h2>#{selectedOrder.id}</h2></div><Tag color={statusColor(selectedOrder.status)}>{orderStatusLabel(selectedOrder.status)}</Tag></div>
        <Typography.Paragraph type="secondary">{selectedOrder.customer?.nickname || '顾客'} {selectedOrder.customer?.phone_masked || ''}</Typography.Paragraph>
        <List header="服务项目" dataSource={selectedOrder.items || []} locale={{ emptyText: '当前暂无服务项目' }} renderItem={(item: any) => <List.Item><span>{technicianOrderItemLabel(item)}</span><span>×{item.quantity || 1}</span></List.Item>} />
        <div className="technician-task-card-foot">
          {selectedOccupancyId !== null && selectedOrder.customer?.id && <Button block size="large" icon={<EyeOutlined />} onClick={() => { setReferenceOccupancyId(selectedOccupancyId); setSelectedOrder(undefined); }}>查看上次服务参考</Button>}
          {selectedActions.includes('confirm') && <Button type="primary" block size="large" icon={<PlayCircleOutlined />} loading={acting === selectedOccupancyId} onClick={() => void act(selectedOrder, 'confirm')}>确认服务</Button>}
          {selectedActions.includes('finish') && <Button type="primary" block size="large" icon={<CheckCircleOutlined />} loading={acting === selectedOccupancyId} onClick={() => void act(selectedOrder, 'finish')}>服务结束</Button>}
          {selectedOccupancyId === null && <Typography.Text type="secondary">当前服务单接口未提供服务位占用凭证，仅支持查看。</Typography.Text>}
          {selectedOrder.completed_by_me && selectedOrder.customer?.id && selectedOrder.selection_session_id && <Button block size="large" onClick={() => { setProfileOrder(selectedOrder); setSelectedOrder(undefined); }}>填写服务参考</Button>}
        </div>
        </>}
      </div>}
    </Drawer>
    <TechnicianProfileSheet task={profileOrder} onClose={() => setProfileOrder(undefined)} onSaved={() => { setProfileOrder(undefined); void load(); }} />
    <TechnicianServiceReferenceDrawer occupancyId={referenceOccupancyId} open={referenceOccupancyId !== null} onClose={() => setReferenceOccupancyId(null)} />
  </div>;
}

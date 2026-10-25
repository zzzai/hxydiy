import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, Empty, Spin, Tag } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { getManagerServiceOrders } from '../api';

type ServiceOrderStatus = 'waiting_service' | 'in_service' | 'completed';
type ServiceOrder = {
  occupancy_id: number;
  room_name: string;
  occupancy_status: string;
  technician_name: string | null;
  items: Array<{ name: string; quantity: number }>;
  actual_start_at: string | null;
  actual_end_at: string | null;
  created_at: string | null;
};

const STATUS_OPTIONS: Array<{ value: ServiceOrderStatus; label: string; empty: string }> = [
  { value: 'waiting_service', label: '待服务', empty: '当前没有待服务订单' },
  { value: 'in_service', label: '服务中', empty: '当前没有服务中订单' },
  { value: 'completed', label: '今日已完成', empty: '今天还没有已完成服务' },
];

function timeText(value?: string | null) {
  if (!value || Number.isNaN(Date.parse(value))) return '—';
  return new Date(value).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
}

export default function ManagerServiceOrdersView({ onOpenPositions, refreshKey = 0 }: { onOpenPositions?: () => void; refreshKey?: number }) {
  const [status, setStatus] = useState<ServiceOrderStatus>('waiting_service');
  const [items, setItems] = useState<ServiceOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const active = useRef(true);
  const request = useRef(0);
  const loadingRef = useRef(false);

  const load = useCallback(async () => {
    if (!active.current || loadingRef.current) return;
    loadingRef.current = true;
    const version = ++request.current;
    setLoading(true);
    try {
      const response = await getManagerServiceOrders(status);
      if (!active.current || version !== request.current) return;
      setItems(Array.isArray(response.data?.items) ? response.data.items : []);
      setError('');
    } catch {
      if (active.current && version === request.current) {
        setItems([]);
        setError('服务单加载失败，请重试');
      }
    } finally {
      loadingRef.current = false;
      if (active.current && version === request.current) setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    active.current = true;
    void load();
    const refresh = () => { if (document.visibilityState === 'visible') void load(); };
    const timer = window.setInterval(refresh, 10000);
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      active.current = false;
      request.current++;
      window.clearInterval(timer);
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [load, refreshKey]);

  const option = STATUS_OPTIONS.find(item => item.value === status)!;
  return <section className="manager-tasks-view manager-service-orders" aria-label="门店服务单">
    <div className="manager-tasks-heading">
      <div><h2>服务单</h2><p>按服务状态查看门店现场，只读；服务状态以技师确认/结束为准。</p></div>
      <Button icon={<ReloadOutlined />} aria-label="刷新服务单" onClick={() => void load()} loading={loading} />
    </div>
    <div className="manager-order-period" role="group" aria-label="服务单状态">
      {STATUS_OPTIONS.map(item => <button key={item.value} type="button" aria-pressed={status === item.value} onClick={() => setStatus(item.value)}>{item.label}</button>)}
    </div>
    {error && <Alert type="error" showIcon message={error} action={<Button onClick={() => void load()}>重试</Button>} />}
    {loading && !items.length ? <div className="manager-empty"><Spin size="small" /><span>正在加载服务单</span></div>
      : !items.length ? <div className="manager-empty"><strong>{option.empty}</strong><span>刷新或切换状态查看其他服务单</span></div>
        : <div className="manager-selection-list">
          {items.map(item => <article className="manager-selection-card" key={item.occupancy_id}>
            <div className="manager-card-top">
              <span>{item.room_name}</span>
              <Tag color={status === 'completed' ? 'blue' : status === 'in_service' ? 'green' : item.technician_name ? 'gold' : 'orange'}>
                {status === 'completed' ? '已完成' : status === 'in_service' ? '服务中' : item.technician_name ? '待服务' : '未分配技师'}
              </Tag>
            </div>
            <ul className="manager-item-list">
              {item.items.length ? item.items.map((line, index) => <li key={index}>{line.name}{line.quantity > 1 ? ` ×${line.quantity}` : ''}</li>) : <li>未填写项目</li>}
            </ul>
            <div className="manager-card-meta">
              <span>{item.technician_name || '待安排技师'}</span>
              <span>{status === 'completed' ? `结束 ${timeText(item.actual_end_at)}` : `进入 ${timeText(item.created_at)}`}</span>
            </div>
            {(status === 'waiting_service' || status === 'in_service') && onOpenPositions && <Button block onClick={onOpenPositions}>查看服务位</Button>}
          </article>)}
        </div>}
  </section>;
}

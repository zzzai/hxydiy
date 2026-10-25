import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, Spin, Tag } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { acknowledgeOperationalException, getFeedback, getManagerWorkbench, getOperationalExceptions, getServiceAnomalies } from '../api';
import { readUnresolvedTasks, type UnresolvedTask } from './managerTasks';
import { useTechnicianSession } from './useTechnicianSession';

function timeText(value?: string | null) {
  if (!value || Number.isNaN(Date.parse(value))) return '时间待核实';
  return new Date(value).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
}

export default function ManagerTasksView({ onOpenReviews, onOpenOrders, onOpenPositions }: { onOpenReviews?: () => void; onOpenOrders?: (staleOnly?: boolean) => void; onOpenPositions?: () => void }) {
  const [reviews, setReviews] = useState<Array<{ id: number; rating: number; note: string; created_at: string | null; customer_phone?: string | null }>>([]);
  const [staleOrders, setStaleOrders] = useState(0);
  const [unassignedServices, setUnassignedServices] = useState(0);
  const [exceptions, setExceptions] = useState<UnresolvedTask[]>([]);
  const [recordFollowUp, setRecordFollowUp] = useState({ pending_count: 0, window_days: 30, technicians: [] as Array<{ technician_id: number; name: string; count: number }> });
  const [serviceAnomalies, setServiceAnomalies] = useState<Array<{ id: number; label: string; room_name: string }>>([]);
  const [acknowledging, setAcknowledging] = useState<number>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const current = useTechnicianSession();
  const request = useRef(0);
  const loadingRef = useRef(false);
  const acknowledgingRef = useRef(false);
  const [actionError, setActionError] = useState('');

  const load = useCallback(async () => {
    if (!current()) return;
    const version = ++request.current;
    loadingRef.current = true;
    setLoading(true);
    try {
      const [reviewsResponse, workbenchResponse, exceptionsResponse, anomaliesResponse] = await Promise.all([
        getFeedback({ feedback_type: 'service_review', follow_up_status: 'open', page: 1, page_size: 20 }),
        getManagerWorkbench(),
        getOperationalExceptions('unresolved'),
        getServiceAnomalies(),
      ]);
      if (!current() || request.current !== version) return;
      const unresolved = readUnresolvedTasks(exceptionsResponse.data);
      const followUp = workbenchResponse.data?.record_follow_up;
      if (!followUp || !Array.isArray(followUp.technicians) || !Number.isSafeInteger(followUp.pending_count)) throw new Error('Invalid record follow-up response');
      setReviews(Array.isArray(reviewsResponse.data?.items) ? reviewsResponse.data.items.filter((item: { rating: number }) => item.rating <= 2) : []);
      setStaleOrders(Number(workbenchResponse.data?.attention?.find((item: { key: string }) => item.key === 'stale_order')?.count) || 0);
      setUnassignedServices(Number(workbenchResponse.data?.attention?.find((item: { key: string }) => item.key === 'unassigned_service')?.count) || 0);
      setExceptions(unresolved);
      setRecordFollowUp(followUp);
      setServiceAnomalies(Array.isArray(anomaliesResponse.data?.items) ? anomaliesResponse.data.items : []);
      setError('');
    } catch {
      if (current() && request.current === version) setError('待处理事项加载失败，请重试');
    } finally {
      if (request.current === version) {
        loadingRef.current = false;
        if (current()) setLoading(false);
      }
    }
  }, [current]);

  const acknowledge = async (id: number) => {
    if (!current() || acknowledgingRef.current) return;
    acknowledgingRef.current = true;
    setActionError('');
    setAcknowledging(id);
    try {
      await acknowledgeOperationalException(id);
      if (!current()) return;
      setExceptions(items => items.map(item => item.id === id ? { ...item, status: 'acknowledged' } : item));
      await load();
    } catch {
      if (current()) setActionError('未能确认知悉，请重试；事项仍保留在列表中。');
    } finally {
      acknowledgingRef.current = false;
      if (current()) setAcknowledging(undefined);
    }
  };

  useEffect(() => {
    void load();
    const refresh = () => {
      if (document.visibilityState === 'visible' && !loadingRef.current && !acknowledgingRef.current) void load();
    };
    window.addEventListener('pageshow', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      request.current++;
      window.removeEventListener('pageshow', refresh);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [load]);
  const count = reviews.length + staleOrders + unassignedServices + exceptions.length + recordFollowUp.pending_count + serviceAnomalies.length;

  return <section className="manager-tasks-view">
    <div className="manager-tasks-heading">
      <div><h2>待处理 <span>{count}</span></h2><p>跟进服务安排、记录补填、已发现的异常和顾客评价。</p></div>
      <Button icon={<ReloadOutlined />} aria-label="刷新待处理" onClick={() => void load()} loading={loading} />
    </div>
    {error && <Alert type="error" showIcon message={error} action={<Button onClick={() => void load()}>重试</Button>} />}
    {actionError && <Alert type="error" showIcon message={actionError} />}
    {loading && !count ? <div className="manager-empty"><Spin size="small" /><span>正在加载待处理</span></div>
      : <>
        {!error && !count && <div className="manager-empty"><strong>当前没有待处理</strong><span>返回本页时自动刷新，也可手动刷新查看最新情况</span></div>}
        {unassignedServices > 0 && <div className="manager-task-stale">
          <div className="manager-task-top"><span>待服务订单尚未分配技师</span><Tag color="orange">{unassignedServices}</Tag></div>
          <p>由店长现场核对服务位并安排技师；安排后状态会同步到技师端。</p>
          <Button block onClick={onOpenPositions}>查看服务位</Button>
        </div>}
        {exceptions.length > 0 && <div className="manager-review-tasks">
          <div className="manager-task-top"><span>漏单与状态不一致</span><Tag color="red">{exceptions.length}</Tag></div>
          {exceptions.map(item => <div className="manager-review-task-row" key={item.id}>
            <span><strong>{item.label}</strong><Tag>{item.status === 'acknowledged' ? '已知悉 · 待处理' : '待核对'}</Tag></span>
            <span>{item.assigned_to ? `处理人 ${item.assigned_to}` : '待指派'}{item.due_at ? ` · 截止 ${timeText(item.due_at)}` : ''}{item.overdue ? ' · 已逾期' : ''}</span>
            {item.status === 'open' && <Button size="small" disabled={acknowledging !== undefined} loading={acknowledging === item.id} onClick={() => void acknowledge(item.id)}>确认知悉</Button>}
          </div>)}
          <p>知悉不代表问题已解决，事项仍会保留。请先核对本店服务单；处理结果由异常中心记录。</p>
          <Button block onClick={() => onOpenOrders?.(false)}>查看本店服务单</Button>
        </div>}
        {serviceAnomalies.length > 0 && <div className="manager-review-tasks">
          <div className="manager-task-top"><span>服务位关联异常</span><Tag color="red">{serviceAnomalies.length}</Tag></div>
          {serviceAnomalies.map(item => <div className="manager-review-task-row" key={item.id}>
            <span><strong>{item.label}</strong> {item.room_name}</span>
            <Button size="small" onClick={onOpenPositions}>查看服务位</Button>
          </div>)}
          <p>由店长到现场核对服务位与选单；本项只读检测，不自动修改服务状态。</p>
        </div>}
        {recordFollowUp.pending_count > 0 && <div className="manager-review-tasks">
          <div className="manager-task-top"><span>近 {recordFollowUp.window_days} 天服务记录待补填</span><Tag color="orange">{recordFollowUp.pending_count}</Tag></div>
          {recordFollowUp.technicians.map(item => <div className="manager-review-task-row" key={item.technician_id}>
            <span>{item.name}</span><span>{item.count} 次服务待填写</span>
          </div>)}
          <p>请提醒对应技师进入“历史服务”，选择“只看待填写”补填。记录保存后自动移出待办，无需等待顾客确认。</p>
        </div>}
        {staleOrders > 0 && <div className="manager-task-stale">
          <div className="manager-task-top"><span>超过 30 分钟未开始</span><Tag color="red">{staleOrders}</Tag></div>
          <p>请核对现场是否已安排服务，避免顾客一直等待。</p>
          <Button block onClick={() => onOpenOrders?.(true)}>查看超时订单</Button>
        </div>}
        {reviews.length > 0 && <div className="manager-review-tasks">
          <div className="manager-task-top"><span>低分评价待跟进</span><Tag color="red">{reviews.length}</Tag></div>
          {reviews.map(review => <button type="button" className="manager-review-task-row" key={review.id} onClick={onOpenReviews}>
            <span><strong>{review.rating} 星</strong> {review.note || '顾客未填写文字'}{review.customer_phone ? ' · ' + review.customer_phone : ''}</span><time>{timeText(review.created_at)}</time>
          </button>)}
          <Button block onClick={onOpenReviews}>去处理评价</Button>
        </div>}
      </>}
  </section>;
}

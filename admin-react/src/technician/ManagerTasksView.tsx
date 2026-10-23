import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Spin, Tag } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { acknowledgeOperationalException, getFeedback, getManagerWorkbench, getOperationalExceptions } from '../api';

function timeText(value?: string | null) {
  if (!value || Number.isNaN(Date.parse(value))) return '时间待核实';
  return new Date(value).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
}

/** 店长只处理门店评价与超时提醒；订单确认/超时由系统负责，不在端上操作。 */
const EXCEPTION_LABELS: Record<string, string> = {
  missing_selection: '服务订单缺选单',
  missing_order: '选单缺履约订单',
  amount_mismatch: '选单与订单金额不一致',
};

export default function ManagerTasksView({ onOpenReviews, onOpenOrders, onOpenPositions }: { onOpenReviews?: () => void; onOpenOrders?: () => void; onOpenPositions?: () => void }) {
  const [reviews, setReviews] = useState<Array<{ id: number; rating: number; note: string; created_at: string | null; customer_phone?: string | null }>>([]);
  const [staleOrders, setStaleOrders] = useState(0);
  const [unassignedServices, setUnassignedServices] = useState(0);
  const [exceptions, setExceptions] = useState<Array<{ id: number; exception_type: string; title: string; assigned_to?: string | null; due_at?: string | null; overdue?: boolean }>>([]);
  const [acknowledging, setAcknowledging] = useState<number>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [reviewsResponse, workbenchResponse, exceptionsResponse] = await Promise.all([
        getFeedback({ feedback_type: 'service_review', follow_up_status: 'open', page: 1, page_size: 20 }),
        getManagerWorkbench(),
        getOperationalExceptions('open'),
      ]);
      setReviews(Array.isArray(reviewsResponse.data?.items) ? reviewsResponse.data.items.filter((item: { rating: number }) => item.rating <= 2) : []);
      setStaleOrders(Number(workbenchResponse.data?.attention?.find((item: { key: string }) => item.key === 'stale_order')?.count) || 0);
      setUnassignedServices(Number(workbenchResponse.data?.attention?.find((item: { key: string }) => item.key === 'unassigned_service')?.count) || 0);
      setExceptions(Array.isArray(exceptionsResponse.data?.items) ? exceptionsResponse.data.items : []);
      setError('');
    } catch {
      setError('待处理事项加载失败，请重试');
    } finally {
      setLoading(false);
    }
  }, []);

  const acknowledge = async (id: number) => {
    setAcknowledging(id);
    try { await acknowledgeOperationalException(id); await load(); }
    finally { setAcknowledging(undefined); }
  };

  useEffect(() => { void load(); }, [load]);

  return <section className="manager-tasks-view">
    <div className="manager-tasks-heading">
      <div><h2>待处理 <span>{reviews.length + staleOrders + unassignedServices + exceptions.length}</span></h2><p>漏单、未分配技师、超时和低分评价会进入这里。</p></div>
      <Button icon={<ReloadOutlined />} aria-label="刷新待处理" onClick={() => void load()} loading={loading} />
    </div>
    {error && <Alert type="error" showIcon message={error} action={<Button onClick={() => void load()}>重试</Button>} />}
    {loading && !reviews.length && !staleOrders && !unassignedServices && !exceptions.length ? <div className="manager-empty"><Spin size="small" /><span>正在加载待处理</span></div>
      : <>
        {!reviews.length && !staleOrders && !unassignedServices && !exceptions.length && <div className="manager-empty"><strong>没有待处理</strong><span>漏单、未分配技师、超时和低分评价会在这里出现</span></div>}
        {unassignedServices > 0 && <div className="manager-task-stale">
          <div className="manager-task-top"><span>待服务订单尚未分配技师</span><Tag color="orange">{unassignedServices}</Tag></div>
          <p>由店长现场核对服务位并安排技师；安排后状态会同步到技师端。</p>
          <Button block onClick={onOpenPositions}>查看服务位</Button>
        </div>}
        {exceptions.length > 0 && <div className="manager-review-tasks">
          <div className="manager-task-top"><span>漏单与状态不一致</span><Tag color="red">{exceptions.length}</Tag></div>
          {exceptions.map(item => <div className="manager-review-task-row" key={item.id}>
            <span><strong>{EXCEPTION_LABELS[item.exception_type] || '需要核对的经营异常'}</strong> {item.title}</span>
            <span>{item.assigned_to ? `处理人 ${item.assigned_to}` : '待指派'}{item.due_at ? ` · 截止 ${timeText(item.due_at)}` : ''}{item.overdue ? ' · 已逾期' : ''}</span>
            <Button size="small" loading={acknowledging === item.id} onClick={() => void acknowledge(item.id)}>确认知悉</Button>
          </div>)}
          <p>确认后会记录处理人和时间；具体修正仍在异常中心完成。</p>
        </div>}
        {staleOrders > 0 && <div className="manager-task-stale">
          <div className="manager-task-top"><span>超过 30 分钟未开始</span><Tag color="red">{staleOrders}</Tag></div>
          <p>订单确认和超时由系统自动处理；可查看订单详情了解现场状态。</p>
          <Button block onClick={onOpenOrders}>查看超时订单</Button>
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

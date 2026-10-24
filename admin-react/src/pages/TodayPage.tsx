import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Descriptions, Drawer, Empty, Space, Spin, Statistic, Table, Tag, Typography } from 'antd';
import { ReloadOutlined, RightOutlined } from '@ant-design/icons';
import { getLiveServicePositionMap, getManagerWorkbench, getOrderReconciliation, getStaff, getSelectionSessions } from '../api';
import { canViewReadOnlyOperations } from '../auth';
import { type LiveServicePositionMap, type ServicePosition, type SelectionSummary } from '../servicePositions';
import { attentionDestination, displayCount, operationTime, serviceStatus } from '../dailyOperations';
import './daily-operations.css';

type Workbench = { generated_at?: string; summary: Record<string, number>; attention: Array<{ key: string; label: string; count: number }>; record_follow_up?: { pending_count: number; window_days: number; technicians: Array<{ technician_id: number; name: string; count: number }> } };
type Reconciliation = { summary: { anomaly_count: number; orders_checked: number; selections_checked: number } };
const itemNames = (items: SelectionSummary['items']) => items.map(item => `${item.name || '服务项目'}${(item.quantity || 0) > 1 ? ` ×${item.quantity}` : ''}`).join('、');
const taskCopy: Record<string, { label: string; hint: string; action: string }> = {
  stale_order: { label: '超过30分钟的选单待核实', hint: '核对现场是否已开始服务，历史未完成事项也可能计入。', action: '核对选单' },
  low_review: { label: '低分评价待跟进', hint: '查看顾客反馈，记录本次处理结果。', action: '查看评价' },
  unassigned_service: { label: '待服务项目尚未安排技师', hint: '查看对应服务位并核对现场安排。', action: '查看服务位' },
  record_pending: { label: '近30天服务记录待补填', hint: '按技师查看缺少的记录，由服务技师本人补填。', action: '查看待补记录' },
  exception_queue: { label: '服务信息待核对', hint: '已知悉的事项也会保留，直到记录处理结果。', action: '去处理' },
  exception_overdue: { label: '服务待办已逾期', hint: '属于未处理事项，请优先跟进，不重复计为新问题。', action: '查看待办' },
};
export default function TodayPage() {
  const navigate = useNavigate();
  const readOnly = canViewReadOnlyOperations(getStaff()?.role);
  const [board, setBoard] = useState<LiveServicePositionMap | null>(null);
  const [workbench, setWorkbench] = useState<Workbench | null>(null);
  const [reconciliation, setReconciliation] = useState<Reconciliation | null>(null);
  const [appointments, setAppointments] = useState<Array<{ id: string; status: string; submitted_at?: string; position?: { status: string }; items: SelectionSummary['items'] }>>([]);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<string[]>([]);
  const [recordsOpen, setRecordsOpen] = useState(false);
  const version = useRef(0);
  const load = useCallback(async () => {
    const current = ++version.current;
    setLoading(true); setErrors([]);
    if (readOnly) {
      try {
        const response = await getSelectionSessions(undefined, undefined, { page: 1, page_size: 100 }, true);
        if (!Array.isArray(response.data?.items)) throw new Error('Invalid appointment response');
        if (current === version.current) setAppointments(response.data.items);
      } catch { if (current === version.current) { setAppointments([]); setErrors(['今日安排加载失败']); } }
      finally { if (current === version.current) setLoading(false); }
      return;
    }
    const result = await Promise.allSettled([
      getManagerWorkbench().then(response => { if (!response.data?.summary || !Array.isArray(response.data.attention)) throw new Error('Invalid workbench response'); return response.data as Workbench; }),
      getLiveServicePositionMap().then(response => { if (!Array.isArray(response.data?.positions)) throw new Error('Invalid position response'); return response.data; }),
      getOrderReconciliation(30).then(response => { if (displayCount(response.data?.summary?.anomaly_count) === '—') throw new Error('Invalid reconciliation response'); return response.data as Reconciliation; }),
    ]);
    if (current !== version.current) return;
    setWorkbench(result[0].status === 'fulfilled' ? result[0].value : null);
    setBoard(result[1].status === 'fulfilled' ? result[1].value : null);
    setReconciliation(result[2].status === 'fulfilled' ? result[2].value : null);
    setErrors(result.flatMap((item, index) => item.status === 'rejected' ? [['待办与服务概况加载失败', '在店服务加载失败', '服务信息核对暂时不可用'][index]] : []));
    setLoading(false);
  }, [readOnly]);
  useEffect(() => { void load(); return () => { version.current++; }; }, [load]);
  const metric = (key: string) => loading ? '—' : displayCount(workbench?.summary[key]);
  return <div className="daily-page">
    <div className="page-heading"><div><h2>今日工作台</h2><div className="page-kicker">{readOnly ? '查看本店待跟进选单（最近100条）' : '先处理待办，再跟进门店服务。今日按北京时间统计。'}</div></div><Space wrap>{workbench?.generated_at && <Typography.Text type="secondary">更新于 {operationTime(workbench.generated_at)}</Typography.Text>}<Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>刷新工作台</Button></Space></div>
    {errors.length > 0 && <Alert type="warning" showIcon message={errors.join('；')} description="未获取的数据不计为0，也不表示没有待办。其他已加载内容可继续查看。" action={<Button onClick={() => void load()}>重试加载</Button>} />}
    {readOnly ? <section className="daily-panel"><h3>待跟进选单</h3>{loading ? <Spin /> : !errors.length && <Table rowKey="id" dataSource={appointments} pagination={{ pageSize: 10 }} columns={[{ title: '项目', render: (_, row) => itemNames(row.items || []) || '到店服务' }, { title: '安排时间', render: (_, row) => operationTime(row.submitted_at) }, { title: '进度', render: (_, row) => serviceStatus(row.position?.status || row.status) }]} />}</section> : <>
    <div className="daily-metrics">{[['今日选单', 'today_orders'], ['待服务', 'waiting_service'], ['服务中', 'in_service'], ['今日完成', 'completed_today']].map(([label, key]) => <Statistic key={key} title={label} value={metric(key)} />)}</div>
    <div className="daily-columns">
      <section className="daily-panel"><div className="daily-panel-heading"><h3>门店待处理</h3><Typography.Text type="secondary">包含历史未完成事项</Typography.Text></div>
        {loading ? <Spin /> : !workbench ? <p className="daily-muted">待办暂未加载，请重试后核对。</p> : workbench.attention.length ? workbench.attention.map(item => {
          const copy = taskCopy[item.key] || { label: '门店事项待核实', hint: '请联系当班负责人核对。', action: '' };
          const target = attentionDestination(item.key);
          return <div className="daily-task" key={item.key}><div><strong>{copy.label}</strong><span>{copy.hint}</span></div><Tag color={item.key === 'exception_overdue' ? 'error' : 'default'}>{displayCount(item.count)}</Tag>{(target || item.key === 'record_pending') && <Button type="link" onClick={() => target ? navigate(target) : setRecordsOpen(true)}>{copy.action}<RightOutlined /></Button>}</div>;
        }) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前没有已登记的待办" />}
      </section>
      <section className="daily-panel daily-check"><h3>服务信息核对</h3><p>检查近30天选单是否有关联服务，以及已关联订单的信息是否一致。</p>
        {loading ? <Spin /> : !reconciliation ? <Alert type="warning" message="本次未完成核对" description="不能据此判断没有异常。" /> : <><Tag color={reconciliation.summary.anomaly_count ? 'warning' : 'success'}>{reconciliation.summary.anomaly_count ? `${reconciliation.summary.anomaly_count} 项差异待核对` : '本次核对未发现差异'}</Tag><p>已检查 {displayCount(reconciliation.summary.selections_checked)} 份选单。</p></>}
        <Button block onClick={() => navigate('/exceptions')}>进入服务待办</Button><p className="daily-muted">进入后点击“核对最新服务”更新待办。</p>
      </section>
    </div>
    <section className="daily-panel"><div className="daily-panel-heading"><h3>在店服务</h3><Button onClick={() => navigate('/service-positions')}>查看服务位</Button></div>{loading ? <Spin /> : !board ? <p className="daily-muted">服务列表暂未加载。</p> : <Table<ServicePosition> rowKey="id" dataSource={board.positions.filter(position => position.selection && !['available', 'unavailable', 'released'].includes(position.state))} pagination={{ pageSize: 10 }} scroll={{ x: 650 }} columns={[
      { title: '服务项目', render: (_, row) => <Space direction="vertical" size={2}><Typography.Text strong>{itemNames(row.selection?.items || []) || '到店服务'}</Typography.Text><Typography.Text type="secondary">{row.selection?.id}</Typography.Text></Space> },
      { title: '进度', width: 130, render: (_, row) => <Tag>{serviceStatus(row.state)}</Tag> },
      { title: '服务位置', width: 150, render: (_, row) => row.customer_label || row.name },
      { title: '下一步', width: 140, render: () => <Button onClick={() => navigate('/service-positions')}>查看现场安排</Button> },
    ]} locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无已安排服务位的服务，未入座选单请在到店选单查看" /> }} />}</section>
    </>}
    <Drawer rootClassName="daily-drawer" title="服务记录待补填" width={460} open={recordsOpen} onClose={() => setRecordsOpen(false)}>
      <p>请对应技师进入技师端“历史服务”，选择“只看待填写”补齐记录。店长查看进度，不代写技师私人记录。</p>
      {workbench?.record_follow_up ? <><p>近 {workbench.record_follow_up.window_days} 天共 {workbench.record_follow_up.pending_count} 次服务待填写。</p><Descriptions column={1} items={workbench.record_follow_up.technicians.map(item => ({ key: item.technician_id, label: item.name, children: `${item.count} 次待填写` }))} /></> : <Alert type="warning" message="暂未获取明细，请刷新工作台后重试。" />}
    </Drawer>
  </div>;
}

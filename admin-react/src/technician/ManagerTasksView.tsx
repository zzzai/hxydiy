import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Drawer, Input, Spin, Tag } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { approveSelectionChangeRequest, getSelectionChangeRequests, rejectSelectionChangeRequest } from '../api';
import { selectionChangeItemSummary } from '../selectionChanges';
import type { ManagerChange } from './managerMobile';

function timeText(value?: string) {
  if (!value || Number.isNaN(Date.parse(value))) return '时间待核实';
  return new Date(value).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
}

/** 店长处理顾客加选；正常订单只在订单页查看，不进入待处理。 */
export default function ManagerTasksView({ onChanged }: { onChanged?: () => void }) {
  const [rows, setRows] = useState<ManagerChange[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<ManagerChange | null>(null);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await getSelectionChangeRequests();
      setRows(Array.isArray(response.data?.items) ? response.data.items : []);
      setError('');
    } catch {
      setError('待处理加选加载失败，请重试');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const act = async (kind: 'approve' | 'reject') => {
    if (!selected || busy) return;
    if (kind === 'reject' && !reason.trim()) return;
    setBusy(true);
    try {
      if (kind === 'approve') await approveSelectionChangeRequest(selected.id);
      else await rejectSelectionChangeRequest(selected.id, reason.trim());
      setSelected(null); setReason('');
      await load(); onChanged?.();
    } finally {
      setBusy(false);
    }
  };

  return <section className="manager-tasks-view">
    <div className="manager-tasks-heading">
      <div><h2>待处理 <span>{rows.length}</span></h2><p>只显示需要店长决定的顾客加选。</p></div>
      <Button icon={<ReloadOutlined />} aria-label="刷新待处理" onClick={() => void load()} loading={loading} />
    </div>
    {error && <Alert type="error" showIcon message={error} action={<Button onClick={() => void load()}>重试</Button>} />}
    {loading && !rows.length ? <div className="manager-empty"><Spin size="small" /><span>正在加载待处理</span></div>
      : !rows.length ? <div className="manager-empty"><strong>没有待处理</strong><span>顾客加选提交后会在这里出现</span></div>
        : <div className="manager-task-list">{rows.map(row => <button type="button" className="manager-task-card" key={row.id} onClick={() => { setSelected(row); setReason(''); }}>
          <div className="manager-task-top"><span>顾客加选</span><Tag color="gold">待确认</Tag></div>
          <strong>{row.revision.added_items.length ? selectionChangeItemSummary(row.revision.added_items[0]) : '新增项目'}</strong>
          <ul className="manager-task-items">{row.revision.added_items.map((item, index) => <li key={index}>{selectionChangeItemSummary(item)}</li>)}</ul>
          <div className="manager-task-meta"><span>订单 · {row.selection.id.slice(-8)}</span><time>{timeText(row.created_at)}</time></div>
        </button>)}</div>}
    <Drawer title="处理顾客加选" placement="bottom" height="min(90dvh, 760px)" rootClassName="manager-detail-drawer" open={Boolean(selected)} onClose={() => setSelected(null)} destroyOnClose footer={<div className="manager-detail-actions"><Button size="large" disabled={busy} onClick={() => { setSelected(null); setReason(''); }}>关闭详情</Button><Button size="large" danger disabled={busy || !reason.trim()} loading={busy} onClick={() => void act('reject')}>拒绝加选</Button><Button size="large" type="primary" disabled={busy} loading={busy} onClick={() => void act('approve')}>确认加选</Button></div>}>
      {selected && <>
        <div className="manager-detail-intro"><span>顾客加选</span><Tag color="gold">待确认</Tag></div>
        <span className="manager-order-code">订单 · {selected.selection.id.slice(-8)}</span>
        <ul className="manager-task-items">{selected.revision.added_items.map((item, index) => <li key={index}>{selectionChangeItemSummary(item)}</li>)}</ul>
        <p className="manager-detail-note">确认后加选项目加入本次服务；拒绝必须填写原因。</p>
        <label className="manager-action-form">拒绝原因<Input.TextArea value={reason} maxLength={256} autoSize={{ minRows: 3, maxRows: 6 }} onChange={event => setReason(event.target.value)} placeholder="仅在拒绝时填写，说明本次不能加选的原因" /></label>
      </>}
    </Drawer>
  </section>;
}

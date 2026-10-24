import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, App, Button, Descriptions, Drawer, Empty, Input, Segmented, Space, Table, Tag, Typography } from 'antd';
import { ReloadOutlined, SyncOutlined } from '@ant-design/icons';
import { acknowledgeOperationalException, assignOperationalException, getOperationalExceptions, resolveOperationalException, syncOrderReconciliation } from '../api';
import { exceptionLabel, exceptionStatus, operationTime, readExceptions, type OperationalException } from '../dailyOperations';
import './daily-operations.css';

export default function ExceptionsPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [items, setItems] = useState<OperationalException[]>([]);
  const [filter, setFilter] = useState('unresolved');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const lock = useRef(false);
  const version = useRef(0);
  const [selected, setSelected] = useState<OperationalException | null>(null);
  const [note, setNote] = useState('');
  const [actionError, setActionError] = useState('');
  const load = useCallback(async () => {
    const current = ++version.current;
    setLoading(true); setError('');
    try {
      const response = await getOperationalExceptions(filter);
      const rows = readExceptions(response.data);
      if (current === version.current) setItems(rows);
    } catch { if (current === version.current) { setItems([]); setError('待办加载失败，暂时无法确认是否还有未处理事项。'); } }
    finally { if (current === version.current) setLoading(false); }
  }, [filter]);
  useEffect(() => { setItems([]); void load(); return () => { version.current++; }; }, [load]);
  const run = async (key: string, request: () => Promise<unknown>, success: string, close = false) => {
    if (lock.current) return;
    lock.current = true; setBusy(key); setActionError('');
    try {
      await request(); message.success(success);
      if (close) { setSelected(null); setNote(''); }
      await load();
    } catch { setActionError('操作未完成，请重试。填写的处理说明已保留。'); }
    finally { lock.current = false; setBusy(''); }
  };
  return <div className="daily-page">
    <div className="page-heading"><div><h2>服务待办</h2><div className="page-kicker">核对漏单与服务信息，跟进到有明确处理结果。</div></div><Space wrap>
      <Button icon={<SyncOutlined />} loading={busy === 'sync'} disabled={!!busy && busy !== 'sync'} onClick={() => void run('sync', () => syncOrderReconciliation(30), '近30天服务信息已核对，待办已更新')}>核对最新服务</Button>
      <Button icon={<ReloadOutlined />} loading={loading} disabled={!!busy} onClick={() => void load()}>刷新列表</Button>
    </Space></div>
    <div className="daily-note">确认知悉后，事项仍保留在未处理列表。核对完成后填写处理说明；这里不会自动修改选单、服务进度或金额。</div>
    <section className="daily-panel">
      <div className="daily-panel-heading"><Segmented aria-label="待办状态" value={filter} disabled={!!busy} onChange={value => setFilter(String(value))} options={[{ label: '未处理', value: 'unresolved' }, { label: '待核对', value: 'open' }, { label: '已知悉', value: 'acknowledged' }, { label: '处理记录', value: 'resolved' }]} /><Typography.Text type="secondary">仅当前门店</Typography.Text></div>
      {error ? <Alert type="error" showIcon message={error} action={<Button onClick={() => void load()}>重试加载</Button>} /> : <>
      {actionError && !selected && <Alert type="error" showIcon message={actionError} />}
      {items.length >= 200 && <Alert type="warning" message="当前仅显示最近200条，请按状态核对；这不是全部历史记录。" />}
      <Table<OperationalException> rowKey="id" loading={loading} dataSource={items} pagination={{ pageSize: 10, showSizeChanger: false }} scroll={{ x: 880 }} locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={filter === 'resolved' ? '还没有处理记录' : '当前列表没有待办，可核对最新服务确认是否有新问题'} /> }} columns={[
        { title: '需要跟进', key: 'issue', render: (_, row) => <Space direction="vertical" size={4}><Typography.Text strong>{exceptionLabel(row.exception_type)}</Typography.Text><Typography.Text type="secondary">{row.entity_type === 'order' ? '服务单' : row.entity_type === 'selection_session' ? '选单' : '服务信息'} · {row.entity_id}</Typography.Text></Space> },
        { title: '状态', width: 160, render: (_, row) => <Tag color={row.status === 'resolved' ? 'success' : row.status === 'acknowledged' ? 'default' : 'warning'}>{exceptionStatus(row.status)}</Tag> },
        { title: '处理人', dataIndex: 'assigned_to', width: 120, render: name => name || '待认领' },
        { title: '处理时限', width: 155, render: (_, row) => <Space direction="vertical" size={2}><span>{row.due_at ? operationTime(row.due_at) : '未设置'}</span>{row.overdue && row.status !== 'resolved' && <Typography.Text type="danger">已逾期，请优先跟进</Typography.Text>}</Space> },
        { title: '操作', width: 210, render: (_, row) => <Space wrap size={4}>
          {row.status === 'open' && <Button size="small" disabled={!!busy} onClick={() => void run(`ack-${row.id}`, () => acknowledgeOperationalException(row.id), '已确认知悉，事项仍保留在未处理列表')}>确认知悉</Button>}
          <Button type="link" disabled={!!busy} onClick={() => { setSelected(row); setNote(row.resolution_note || ''); setActionError(''); }}>{row.status === 'resolved' ? '查看记录' : '跟进处理'}</Button>
        </Space> },
      ]} /></>}
    </section>
    <Drawer rootClassName="daily-drawer" title={selected?.status === 'resolved' ? '处理记录' : '跟进服务待办'} width={480} open={!!selected} onClose={() => { if (!busy) setSelected(null); }} extra={selected?.status !== 'resolved' ? <Button type="primary" loading={busy === 'resolve'} disabled={!!busy || note.trim().length < 2} onClick={() => selected && void run('resolve', () => resolveOperationalException(selected.id, note.trim()), '处理结果已保存，可在处理记录中查看', true)}>保存处理结果</Button> : undefined}>
      {selected && <Space direction="vertical" size={20} style={{ width: '100%' }}>
        <div><Typography.Title level={4}>{exceptionLabel(selected.exception_type)}</Typography.Title><Tag>{exceptionStatus(selected.status)}</Tag></div>
        <Descriptions column={1} items={[{ label: '处理人', children: selected.assigned_to || '待认领' }, { label: '发现时间', children: operationTime(selected.created_at) }, { label: '处理截止', children: operationTime(selected.due_at) }, { label: '知悉时间', children: operationTime(selected.acknowledged_at) }, ...(selected.status === 'resolved' ? [{ label: '完成时间', children: operationTime(selected.resolved_at) }] : [])]} />
        <Button onClick={() => navigate('/selection-sessions')}>查看本店选单</Button>
        {selected.status !== 'resolved' && !selected.assigned_to && <Button disabled={!!busy} onClick={() => void run('assign', async () => { const result = await assignOperationalException(selected.id); setSelected({ ...selected, assigned_to: result.data?.assigned_to || '我' }); }, '已认领，处理人已记录')}>由我跟进</Button>}
        {selected.status === 'resolved' ? <div><Typography.Text strong>处理说明</Typography.Text><Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>{selected.resolution_note || '未填写'}</Typography.Paragraph></div> : <>
          <Alert type="info" showIcon message="先核对原始服务，再保存处理结果" description="保存后仅关闭这条待办，不会修正原业务数据；问题仍存在时，后续核对可能再次发现。" />
          <label htmlFor="exception-note">处理说明</label><Input.TextArea id="exception-note" value={note} onChange={event => setNote(event.target.value)} rows={4} maxLength={500} showCount disabled={!!busy} placeholder="例如：已与当班技师核实，并在原服务单补齐信息。" />
          {actionError && <Alert type="error" showIcon message={actionError} />}
        </>}
      </Space>}
    </Drawer>
  </div>;
}

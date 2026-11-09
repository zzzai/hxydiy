import { useCallback, useEffect, useState } from 'react';
import { App, Button, Input, Modal, Select, Space, Table, Tag, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { getHqAssessments, spotCheckHqAssessment } from '../api';

type Row = {
  id: number; store_id: number; staff_id: number; staff_name: string; course_name: string;
  kind: 'theory' | 'practical'; result: 'pending' | 'passed' | 'failed';
  hq_status: 'pending' | 'passed' | 'returned'; manager_note: string;
  manager_confirmed_at: string | null; hq_note: string; hq_reviewed_at: string | null;
};

const statusText: Record<string, string> = { pending: '待抽检', passed: '抽检通过', returned: '退回复训' };
const statusColor: Record<string, string> = { pending: 'gold', passed: 'green', returned: 'red' };

export default function AssessmentsPage() {
  const { message } = App.useApp();
  const [rows, setRows] = useState<Row[]>([]);
  const [status, setStatus] = useState('pending');
  const [loading, setLoading] = useState(true);
  const [target, setTarget] = useState<Row | null>(null);
  const [result, setResult] = useState<'passed' | 'returned'>('passed');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await getHqAssessments(status);
      setRows(Array.isArray(data?.items) ? data.items : []);
    } catch {
      message.error('考核抽检队列加载失败');
      setRows([]);
    } finally { setLoading(false); }
  }, [status, message]);

  useEffect(() => { void load(); }, [load]);

  const open = (row: Row) => { setTarget(row); setResult('passed'); setNote(''); };

  const submit = async () => {
    if (!target || saving) return;
    setSaving(true);
    try {
      await spotCheckHqAssessment(target.id, { hq_status: result, note: note.trim() });
      message.success(result === 'passed' ? '总部抽检已通过' : '已退回门店复训');
      setTarget(null);
      await load();
    } catch {
      message.error('抽检提交失败，请重试');
    } finally { setSaving(false); }
  };

  return <div>
    <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 12, marginBottom: 16 }}>
      <div>
        <Typography.Title level={3} style={{ margin: 0 }}>考核抽检</Typography.Title>
        <Typography.Paragraph type="secondary" style={{ margin: '4px 0 0' }}>店长确认后的技师考核，由总部抽检通过或退回复训。</Typography.Paragraph>
      </div>
      <Space>
        <Select value={status} onChange={setStatus} style={{ width: 130 }} options={[{ value: 'pending', label: '待抽检' }, { value: 'passed', label: '已通过' }, { value: 'returned', label: '已退回' }]} />
        <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>刷新</Button>
      </Space>
    </div>
    <Table<Row> rowKey="id" loading={loading} dataSource={rows} pagination={false} locale={{ emptyText: '暂无考核记录' }} columns={[
      { title: '技师', dataIndex: 'staff_name', width: 120 },
      { title: '考核项目', dataIndex: 'course_name' },
      { title: '类型', dataIndex: 'kind', width: 80, render: (value) => value === 'practical' ? '实操' : '理论' },
      { title: '店长确认', dataIndex: 'manager_confirmed_at', width: 170, render: (value) => value ? new Date(value).toLocaleString('zh-CN') : '—' },
      { title: '店长备注', dataIndex: 'manager_note', ellipsis: true },
      { title: '状态', dataIndex: 'hq_status', width: 110, render: (value) => <Tag color={statusColor[value]}>{statusText[value]}</Tag> },
      { title: '操作', width: 110, render: (_, row) => <Button size="small" onClick={() => open(row)}>{row.hq_status === 'pending' ? '抽检' : '复核'}</Button> },
    ]} />
    <Modal open={Boolean(target)} title={`总部抽检 · ${target?.staff_name || ''}`} okText="提交" cancelText="取消" confirmLoading={saving} onCancel={() => setTarget(null)} onOk={() => void submit()}>
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <div><Typography.Text strong>{target?.course_name}</Typography.Text><br /><Typography.Text type="secondary">{target?.manager_note || '店长未填写备注'}</Typography.Text></div>
        <Select value={result} onChange={setResult} style={{ width: '100%' }} options={[{ value: 'passed', label: '抽检通过' }, { value: 'returned', label: '退回复训' }]} />
        <Input.TextArea value={note} onChange={(event) => setNote(event.target.value)} rows={3} maxLength={500} placeholder="抽检意见（可选）" />
      </Space>
    </Modal>
  </div>;
}

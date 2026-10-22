import { useEffect, useState } from 'react';
import { App, Button, Card, Input, Modal, Space, Table, Tag } from 'antd';
import { ReloadOutlined, SyncOutlined } from '@ant-design/icons';
import { getOperationalExceptions, resolveOperationalException, syncOrderReconciliation } from '../api';

const TYPE_LABELS: Record<string, string> = {
  missing_selection: '服务订单缺选单',
  missing_order: '选单缺履约订单',
  status_mismatch: '状态不一致',
  amount_mismatch: '金额不一致',
};

export default function ExceptionsPage() {
  const { message } = App.useApp();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [resolving, setResolving] = useState<any>();
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const response = await getOperationalExceptions('open');
      setItems(response.data?.items || []);
    } catch { message.error('异常队列加载失败'); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);

  const sync = async () => {
    setSyncing(true);
    try {
      const response = await syncOrderReconciliation(30);
      const data = response.data || {};
      message.success(`对账同步完成：新增 ${data.created || 0} 条，更新 ${data.updated || 0} 条`);
      await load();
    } catch { message.error('对账同步失败，请稍后重试'); }
    finally { setSyncing(false); }
  };

  const resolve = async () => {
    if (!resolving) return;
    if (note.trim().length < 2) { message.error('请填写至少 2 个字的处理说明'); return; }
    setSaving(true);
    try {
      await resolveOperationalException(resolving.id, note.trim());
      message.success('异常已处理');
      setResolving(undefined); setNote('');
      await load();
    } catch { message.error('处理失败，请稍后重试'); }
    finally { setSaving(false); }
  };

  return <div>
    <div className="page-heading">
      <div>
        <h2>异常处理</h2>
        <div className="page-kicker">把选单/订单对账差异变成有人处理、可关闭的工作项</div>
      </div>
      <Space>
        <Button icon={<SyncOutlined />} loading={syncing} onClick={() => void sync()}>同步对账异常</Button>
        <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>刷新</Button>
      </Space>
    </div>
    <Card>
      <Table
        rowKey="id"
        loading={loading}
        dataSource={items}
        pagination={false}
        locale={{ emptyText: '当前没有待处理异常；可点击「同步对账异常」拉取最新差异。' }}
        columns={[
          { title: '类型', dataIndex: 'exception_type', width: 160, render: (value: string) => <Tag color={value === 'amount_mismatch' ? 'orange' : 'red'}>{TYPE_LABELS[value] || value}</Tag> },
          { title: '问题', dataIndex: 'title', ellipsis: true },
          {
            title: '对象', width: 220, render: (_: any, row: any) => <span style={{ color: 'var(--hxy-text-secondary)' }}>
              {row.entity_type === 'order' ? '订单' : row.entity_type === 'selection_session' ? '选单' : '对账'} #{row.entity_id}
            </span>,
          },
          { title: '状态', dataIndex: 'status', width: 90, render: () => <Tag color="gold">待处理</Tag> },
          { title: '发现时间', dataIndex: 'created_at', width: 170, render: (value: string) => value?.slice(0, 19).replace('T', ' ') || '-' },
          { title: '操作', width: 90, render: (_: any, row: any) => <Button size="small" type="link" onClick={() => { setResolving(row); setNote(''); }}>处理</Button> },
        ]}
      />
    </Card>
    <Modal title="处理异常" open={Boolean(resolving)} onCancel={() => setResolving(undefined)} onOk={() => void resolve()} okText="确认处理" confirmLoading={saving} okButtonProps={{ disabled: note.trim().length < 2 }}>
      <p style={{ marginTop: 0 }}>{resolving?.title}</p>
      <Input.TextArea rows={3} maxLength={500} showCount value={note} onChange={(event) => setNote(event.target.value)} placeholder="记录核对结果、修正动作或后续责任人" />
    </Modal>
  </div>;
}

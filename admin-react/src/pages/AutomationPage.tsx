import { useState, useEffect } from 'react';
import { App, Button, Card, Table, Tag, Space, Modal, Form, Input, Select, InputNumber, Switch, Popconfirm, Typography } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { getAutomations, createAutomation, updateAutomation, deleteAutomationRule, getAutomationLogs } from '../api';
import StoreScopeSelect from '../components/StoreScopeSelect';

const TRIGGER_MAP: Record<string, string> = {
  new_user: '新用户注册', first_order: '首单完成', order_completed: '服务完成',
  no_visit_30d: '30天未访问', member_expiring: '会员即将到期', high_spender: '高客单价',
};

export default function AutomationPage() {
  const { message } = App.useApp();
  const [data, setData] = useState<any[]>([]);
  const [storeId, setStoreId] = useState<number>();
  const [open, setOpen] = useState(false);
  const [logRule, setLogRule] = useState<any>();
  const [logs, setLogs] = useState<any[]>([]);
  const [logTotal, setLogTotal] = useState(0);
  const [logLoading, setLogLoading] = useState(false);
  const [form] = Form.useForm();

  const load = async () => { try { const r = await getAutomations(storeId); setData(r.data || []); } catch {} };
  useEffect(() => { load(); }, [storeId]);

  const openLogs = async (rule: any) => {
    setLogRule(rule); setLogs([]); setLogTotal(0); setLogLoading(true);
    try {
      const response = await getAutomationLogs(rule.id, storeId, 1, 50);
      setLogs(response.data?.items || []);
      setLogTotal(response.data?.total || 0);
    } catch { message.error('执行日志加载失败'); }
    finally { setLogLoading(false); }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <Space size={12} wrap><span style={{ fontWeight: 600 }}>SCRM 自动化规则</span><StoreScopeSelect value={storeId} onChange={setStoreId} /></Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>新建规则</Button>
      </div>
      <Table dataSource={data} rowKey="id" size="small" pagination={false}
        columns={[
          { title: '名称', dataIndex: 'name' },
          { title: '触发条件', dataIndex: 'trigger_event', width: 120, render: (v: string) => TRIGGER_MAP[v] || v },
          { title: '动作', render: (_: any, r: any) => (r.actions || []).map((a: any, i: number) => <Tag key={i} color="green">{a.type}</Tag>) },
          { title: '冷却', dataIndex: 'cooldown_days', width: 60, render: (v: number) => v ? `${v}天` : '-' },
          { title: '触发次数', dataIndex: 'trigger_count', width: 80 },
          { title: '状态', dataIndex: 'is_enabled', width: 80, render: (v: boolean, r: any) => <Switch checked={v} onChange={async (c) => { await updateAutomation(r.id, { is_enabled: c }, storeId); load(); }} /> },
          { title: '操作', width: 150, render: (_: any, r: any) => <Space size={0}><Button size="small" type="link" onClick={() => void openLogs(r)}>日志</Button><Popconfirm title="确认删除？" onConfirm={async () => { await deleteAutomationRule(r.id, storeId); load(); }}><Button size="small" danger type="link">删除</Button></Popconfirm></Space> },
        ]}
      />
      <Modal open={open} onCancel={() => setOpen(false)} title="新建自动化规则" footer={null} width={500}>
        <Form form={form} onFinish={async (v) => {
          let actions = [];
          try { if (v.actions_text) actions = JSON.parse(`[${v.actions_text}]`); } catch { message.error('动作JSON格式错误'); return; }
          await createAutomation({ name: v.name, description: v.description, trigger_event: v.trigger_event, actions, is_enabled: v.is_enabled !== false, cooldown_days: v.cooldown_days || 0 }, storeId);
          message.success('已创建'); setOpen(false); form.resetFields(); load();
        }} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="trigger_event" label="触发事件" rules={[{ required: true }]} initialValue="new_user">
            <Select options={Object.entries(TRIGGER_MAP).map(([v, l]) => ({ value: v, label: l }))} />
          </Form.Item>
          <Form.Item name="actions_text" label="动作 (JSON)" help='示例: {"type":"grant_coupon","template_code":"xxx"}'><Input placeholder='{"type":"grant_coupon","template_code":"xxx"}' /></Form.Item>
          <Form.Item name="cooldown_days" label="冷却期(天)"><InputNumber min={0} /></Form.Item>
          <Form.Item name="is_enabled" label="启用" valuePropName="checked" initialValue={true}><Switch /></Form.Item>
          <Form.Item name="description" label="描述"><Input /></Form.Item>
          <Button type="primary" htmlType="submit" block>保存</Button>
        </Form>
      </Modal>
      <Modal title={`执行日志 · ${logRule?.name || ''}`} open={Boolean(logRule)} onCancel={() => setLogRule(undefined)} footer={<Button onClick={() => setLogRule(undefined)}>关闭</Button>} width={760}>
        <Typography.Text type="secondary">共 {logTotal} 条；失败原因和动作结果用于排查自动化是否真正生效。</Typography.Text>
        <Table
          style={{ marginTop: 12 }}
          dataSource={logs}
          loading={logLoading}
          rowKey="id"
          size="small"
          pagination={false}
          columns={[
            { title: '时间', dataIndex: 'created_at', width: 170, render: (v: string) => v?.slice(0, 19).replace('T', ' ') || '-' },
            { title: '顾客', width: 150, render: (_: any, r: any) => r.customer || (r.phone_masked || '-') },
            { title: '动作', dataIndex: 'action_type', width: 120 },
            { title: '结果', dataIndex: 'success', width: 80, render: (v: boolean) => <Tag color={v ? 'green' : 'red'}>{v ? '成功' : '失败'}</Tag> },
            { title: '失败原因', dataIndex: 'error_message', ellipsis: true },
          ]}
          locale={{ emptyText: '该规则还没有执行记录' }}
        />
      </Modal>
    </div>
  );
}

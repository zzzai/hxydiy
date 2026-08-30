import { useState, useEffect } from 'react';
import { App, Button, Card, Table, Tag, Space, Modal, Form, Input, Select, InputNumber, Switch, Popconfirm } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { getAutomations, createAutomation, updateAutomation, deleteAutomationRule } from '../api';

const TRIGGER_MAP: Record<string, string> = {
  new_user: '新用户注册', first_order: '首单完成', order_completed: '服务完成',
  no_visit_30d: '30天未访问', member_expiring: '会员即将到期', high_spender: '高客单价',
};

export default function AutomationPage() {
  const { message } = App.useApp();
  const [data, setData] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const load = async () => { try { const r = await getAutomations(); setData(r.data || []); } catch {} };
  useEffect(() => { load(); }, []);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <span style={{ fontWeight: 600 }}>SCRM 自动化规则</span>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>新建规则</Button>
      </div>
      <Table dataSource={data} rowKey="id" size="small" pagination={false}
        columns={[
          { title: '名称', dataIndex: 'name' },
          { title: '触发条件', dataIndex: 'trigger_event', width: 120, render: (v: string) => TRIGGER_MAP[v] || v },
          { title: '动作', render: (_: any, r: any) => (r.actions || []).map((a: any, i: number) => <Tag key={i} color="green">{a.type}</Tag>) },
          { title: '冷却', dataIndex: 'cooldown_days', width: 60, render: (v: number) => v ? `${v}天` : '-' },
          { title: '触发次数', dataIndex: 'trigger_count', width: 80 },
          { title: '状态', dataIndex: 'is_enabled', width: 80, render: (v: boolean, r: any) => <Switch checked={v} onChange={async (c) => { await updateAutomation(r.id, { is_enabled: c }); load(); }} /> },
          { title: '操作', width: 80, render: (_: any, r: any) => <Popconfirm title="确认删除？" onConfirm={async () => { await deleteAutomationRule(r.id); load(); }}><Button size="small" danger type="link">删除</Button></Popconfirm> },
        ]}
      />
      <Modal open={open} onCancel={() => setOpen(false)} title="新建自动化规则" footer={null} width={500}>
        <Form form={form} onFinish={async (v) => {
          let actions = [];
          try { if (v.actions_text) actions = JSON.parse(`[${v.actions_text}]`); } catch { message.error('动作JSON格式错误'); return; }
          await createAutomation({ name: v.name, description: v.description, trigger_event: v.trigger_event, actions, is_enabled: v.is_enabled !== false, cooldown_days: v.cooldown_days || 0 });
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
    </div>
  );
}

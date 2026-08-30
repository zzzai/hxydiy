import { useState, useEffect } from 'react';
import { App, Button, Card, Space, Modal, Form, Input } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { getSegments, createSegment, recountSegment } from '../api';

export default function SegmentsPage() {
  const { message } = App.useApp();
  const [data, setData] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const load = async () => { try { const r = await getSegments(); setData(r.data || []); } catch {} };
  useEffect(() => { load(); }, []);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <span style={{ fontWeight: 600 }}>用户分群</span>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>新建分群</Button>
      </div>
      {data.map((s: any) => (
        <Card key={s.id} size="small" style={{ marginBottom: 12 }} title={<><b>{s.name}</b> <span style={{ color: '#999', marginLeft: 8 }}>{s.user_count}人</span></>}>
          <p style={{ color: '#999', fontSize: 12 }}>{s.description}</p>
          <Space><Button size="small" icon={<ReloadOutlined />} onClick={async () => { await recountSegment(s.id); load(); }}>重新计算</Button></Space>
        </Card>
      ))}
      <Modal open={open} onCancel={() => setOpen(false)} title="新建分群" footer={null}>
        <Form form={form} onFinish={async (v) => {
          let cond = {};
          try { cond = JSON.parse(v.conditions || '{}'); } catch { message.error('JSON格式错误'); return; }
          await createSegment({ name: v.name, description: v.description, conditions: cond });
          message.success('已创建'); setOpen(false); form.resetFields(); load();
        }} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="描述"><Input /></Form.Item>
          <Form.Item name="conditions" label="条件 (JSON)" help='如: {"tags":["高频顾客"],"is_member":true}'><Input.TextArea rows={3} /></Form.Item>
          <Button type="primary" htmlType="submit" block>保存</Button>
        </Form>
      </Modal>
    </div>
  );
}

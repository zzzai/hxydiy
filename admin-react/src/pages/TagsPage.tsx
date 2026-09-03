import { useState, useEffect } from 'react';
import { App, Button, Table, Tag, Space, Modal, Form, Input, Select, Popconfirm } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { getTags, createTag, deleteTag } from '../api';

export default function TagsPage() {
  const { message } = App.useApp();
  const [data, setData] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const load = async () => { try { const r = await getTags(); setData(r.data || []); } catch {} };
  useEffect(() => { load(); }, []);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <span style={{ fontWeight: 600 }}>用户标签</span>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>新建标签</Button>
      </div>
      <Table dataSource={data} rowKey="id" size="small" pagination={false}
        columns={[
          { title: '标签', render: (_: any, r: any) => <Tag color={r.color}>{r.name}</Tag> },
          { title: '类型', dataIndex: 'tag_type', width: 80, render: (v: string) => v === 'auto' ? '自动' : '手动' },
          { title: '人数', dataIndex: 'user_count', width: 60 },
          { title: '描述', dataIndex: 'description' },
          { title: '操作', width: 80, render: (_: any, r: any) => <Popconfirm title="确认删除？" onConfirm={async () => { await deleteTag(r.id); load(); }}><Button size="small" danger type="link">删除</Button></Popconfirm> },
        ]}
      />
      <Modal open={open} onCancel={() => setOpen(false)} title="新建标签" footer={null}>
        <Form form={form} onFinish={async (v) => { await createTag(v); message.success('已创建'); setOpen(false); form.resetFields(); load(); }} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="color" label="颜色" initialValue="#1f8f75"><Input type="color" /></Form.Item>
          <Form.Item name="tag_type" label="类型" initialValue="manual"><Select options={[{ value: 'manual', label: '手动' }, { value: 'auto', label: '自动' }]} /></Form.Item>
          <Form.Item name="description" label="描述"><Input /></Form.Item>
          <Button type="primary" htmlType="submit" block>保存</Button>
        </Form>
      </Modal>
    </div>
  );
}

import { useState, useEffect } from 'react';
import { App, Button, Table, Tag, Space, Modal, Form, Input, Select, InputNumber, Checkbox } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { getCoupons, createCoupon, toggleCouponStatus } from '../api';

export default function CouponsPage() {
  const { message } = App.useApp();
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const load = async () => { setLoading(true); try { const r = await getCoupons(); setData(r.data?.items || []); } catch {} finally { setLoading(false); } };
  useEffect(() => { load(); }, []);

  const onFinish = async (v: any) => {
    await createCoupon({
      ...v, amount_cents: Math.round((v.amount || 0) * 100),
      min_spend_cents: Math.round((v.min_spend || 0) * 100),
      validity_days: v.validity_days || 30,
      status: 'published',
    });
    message.success('已创建并上架'); setOpen(false); form.resetFields(); load();
  };

  const toggle = async (id: number, current: string) => {
    const newStatus = current === 'published' ? 'draft' : 'published';
    await toggleCouponStatus(id, newStatus);
    message.success(newStatus === 'published' ? '已上架' : '已下架');
    load();
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <span style={{ fontWeight: 600 }}>营销券配置</span>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>新建券</Button>
      </div>
      <Table dataSource={data} loading={loading} rowKey="id" size="small" pagination={false}
        columns={[
          { title: '名称', dataIndex: 'name', render: (v: string, r: any) => <b>{v}</b> },
          { title: '面额', width: 100, render: (_: any, r: any) => r.coupon_type === 'percent' ? `${(r.percent_off / 10)}折` : `¥${(r.amount_cents / 100).toFixed(0)}` },
          { title: '门槛', width: 80, render: (_: any, r: any) => r.min_spend_cents > 0 ? `满¥${(r.min_spend_cents / 100).toFixed(0)}` : '无门槛' },
          { title: '有效期', dataIndex: 'validity_days', width: 80, render: (v: number) => `${v}天` },
          { title: '发放', width: 180, render: (_: any, r: any) => (
            <Space size={2} wrap>{r.auto_grant_new_user && <Tag color="blue">新客</Tag>}{r.is_claimable && <Tag color="green">可领</Tag>}{r.daily_claimable && <Tag color="orange">每日</Tag>}{r.auto_apply && <Tag color="purple">满减</Tag>}</Space>
          )},
          { title: '状态', dataIndex: 'status', width: 80, render: (v: string) => <Tag color={v === 'published' ? 'green' : 'default'}>{v === 'published' ? '已上架' : '未上架'}</Tag> },
          { title: '操作', width: 80, render: (_: any, r: any) => <Button size="small" onClick={() => toggle(r.id, r.status)}>{r.status === 'published' ? '下架' : '上架'}</Button> },
        ]}
      />
      <Modal open={open} onCancel={() => setOpen(false)} title="新建营销券" footer={null} width={480}>
        <Form form={form} onFinish={onFinish} layout="vertical">
          <Space style={{ width: '100%' }} direction="vertical">
            <Space><Form.Item name="code" label="编码" rules={[{ required: true }]}><Input /></Form.Item>
            <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item></Space>
            <Space><Form.Item name="coupon_type" label="类型" initialValue="fixed"><Select options={[{ value: 'fixed', label: '满减券' }, { value: 'percent', label: '折扣券' }]} /></Form.Item>
            <Form.Item name="amount" label="面额(元)"><InputNumber min={0} /></Form.Item></Space>
            <Space><Form.Item name="min_spend" label="门槛(元)"><InputNumber min={0} /></Form.Item>
            <Form.Item name="validity_days" label="有效期(天)" initialValue={30}><InputNumber min={1} /></Form.Item></Space>
            <Space><Form.Item name="is_claimable" valuePropName="checked"><Checkbox>领券中心可领</Checkbox></Form.Item>
            <Form.Item name="daily_claimable" valuePropName="checked"><Checkbox>每日可领</Checkbox></Form.Item></Space>
            <Space><Form.Item name="auto_apply" valuePropName="checked"><Checkbox>满减活动(自动立减)</Checkbox></Form.Item>
            <Form.Item name="auto_grant_new_user" valuePropName="checked"><Checkbox>新客自动发</Checkbox></Form.Item></Space>
            <Button type="primary" htmlType="submit" block>保存并上架</Button>
          </Space>
        </Form>
      </Modal>
    </div>
  );
}

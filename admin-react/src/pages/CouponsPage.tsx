import { useState, useEffect } from 'react';
import { App, Button, Table, Tag, Space, Modal, Form, Input, Select, InputNumber, Checkbox } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { getCoupons, createCoupon, getCouponRedemptions, toggleCouponStatus } from '../api';
import StoreScopeSelect from '../components/StoreScopeSelect';

export default function CouponsPage() {
  const { message } = App.useApp();
  const [data, setData] = useState<any[]>([]);
  const [storeId, setStoreId] = useState<number>();
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [detailTemplate, setDetailTemplate] = useState<any>();
  const [detailRows, setDetailRows] = useState<any[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [form] = Form.useForm();

  const openRedemptions = async (template: any) => {
    setDetailTemplate(template); setDetailRows([]); setDetailLoading(true);
    try {
      const response = await getCouponRedemptions(template.id, undefined, storeId);
      setDetailRows(response.data?.items || []);
    } catch { message.error('券明细加载失败'); }
    finally { setDetailLoading(false); }
  };

  const load = async () => { setLoading(true); try { const r = await getCoupons(storeId); setData(r.data?.items || []); } catch {} finally { setLoading(false); } };
  useEffect(() => { load(); }, [storeId]);

  const onFinish = async (v: any) => {
    await createCoupon({
      ...v, amount_cents: Math.round((v.amount || 0) * 100),
      min_spend_cents: Math.round((v.min_spend || 0) * 100),
      validity_days: v.validity_days || 30,
      budget_cents: v.budget ? Math.round(v.budget * 100) : undefined,
      status: 'published',
    }, storeId);
    message.success('已创建并上架'); setOpen(false); form.resetFields(); load();
  };

  const toggle = async (id: number, current: string) => {
    const newStatus = current === 'published' ? 'draft' : 'published';
    await toggleCouponStatus(id, newStatus, storeId);
    message.success(newStatus === 'published' ? '已上架' : '已下架');
    load();
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <Space size={12} wrap><span style={{ fontWeight: 600 }}>营销券配置</span><StoreScopeSelect value={storeId} onChange={setStoreId} /></Space>
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
          { title: '已发/已用', width: 100, render: (_: any, r: any) => `${r.issued_count || 0} / ${r.used_count || 0}` },
          { title: '未用', width: 70, render: (_: any, r: any) => r.unused_count || 0 },
          { title: '使用率', width: 90, render: (_: any, r: any) => r.usage_rate_percent === null || r.usage_rate_percent === undefined ? '—' : `${r.usage_rate_percent}%` },
          { title: '预算', width: 140, render: (_: any, r: any) => r.budget_cents ? `${((r.committed_cents || 0) / 100).toFixed(0)} / ${(r.budget_cents / 100).toFixed(0)} 元` : '不限' },
          { title: '状态', dataIndex: 'status', width: 80, render: (v: string) => <Tag color={v === 'published' ? 'green' : 'default'}>{v === 'published' ? '已上架' : '未上架'}</Tag> },
          { title: '操作', width: 140, render: (_: any, r: any) => <Space size={0}><Button size="small" type="link" onClick={() => void openRedemptions(r)}>明细</Button><Button size="small" onClick={() => toggle(r.id, r.status)}>{r.status === 'published' ? '下架' : '上架'}</Button></Space> },
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
            <Form.Item name="budget" label="预算(元，可不填)" tooltip="固定面额券按已发张数×面额占用预算，超出后停止发放"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item>
            <Space><Form.Item name="is_claimable" valuePropName="checked"><Checkbox>领券中心可领</Checkbox></Form.Item>
            <Form.Item name="daily_claimable" valuePropName="checked"><Checkbox>每日可领</Checkbox></Form.Item></Space>
            <Space><Form.Item name="auto_apply" valuePropName="checked"><Checkbox>满减活动(自动立减)</Checkbox></Form.Item>
            <Form.Item name="auto_grant_new_user" valuePropName="checked"><Checkbox>新客自动发</Checkbox></Form.Item></Space>
            <Button type="primary" htmlType="submit" block>保存并上架</Button>
          </Space>
        </Form>
      </Modal>
      <Modal title={`券明细 · ${detailTemplate?.name || ''}`} open={Boolean(detailTemplate)} onCancel={() => setDetailTemplate(undefined)} footer={<Button onClick={() => setDetailTemplate(undefined)}>关闭</Button>} width={760}>
        <Table
          rowKey="id"
          size="small"
          loading={detailLoading}
          dataSource={detailRows}
          pagination={false}
          locale={{ emptyText: '该券还没有发放记录' }}
          columns={[
            { title: '顾客', width: 150, render: (_: any, row: any) => row.customer || row.phone_masked || '-' },
            { title: '状态', dataIndex: 'status', width: 90, render: (value: string) => <Tag color={value === 'used' ? 'green' : value === 'expired' ? 'default' : 'gold'}>{value === 'used' ? '已使用' : value === 'expired' ? '已过期' : value === 'locked' ? '锁定中' : '未使用'}</Tag> },
            { title: '领取时间', dataIndex: 'claimed_at', width: 170, render: (value: string) => value?.slice(0, 19).replace('T', ' ') || '-' },
            { title: '到期时间', dataIndex: 'expire_at', width: 170, render: (value: string) => value?.slice(0, 19).replace('T', ' ') || '-' },
            { title: '使用订单', dataIndex: 'used_order_id', width: 100, render: (value: number) => value || '-' },
          ]}
        />
      </Modal>
    </div>
  );
}

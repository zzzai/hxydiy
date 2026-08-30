import { useState, useEffect } from 'react';
import { Button, Card, Empty, Input, InputNumber, Modal, Select, Spin, Tag, message } from 'antd';
import { getOrders, getStaff, registerRefundNote } from '../api';
import { buildRefundNotePayload, makeIdempotencyKey } from '../operations';

const STATUS_MAP: Record<string, { color: string; text: string }> = {
  pending_payment: { color: 'red', text: '待门店确认' },
  paid: { color: 'green', text: '待核销' },
  confirmed: { color: 'green', text: '已确认' },
  checked_in: { color: 'orange', text: '已到店' },
  in_service: { color: 'orange', text: '服务中' },
  completed: { color: 'default', text: '已完成' },
};

export default function OrdersPage() {
  const [items, setItems] = useState<any[]>([]);
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [refundOrder, setRefundOrder] = useState<any | null>(null);
  const [refundAmount, setRefundAmount] = useState(0);
  const [refundReasonCode, setRefundReasonCode] = useState('customer_complaint');
  const [refundResponsibility, setRefundResponsibility] = useState('store');
  const [refundReference, setRefundReference] = useState('');
  const [refundReason, setRefundReason] = useState('');
  const [refunding, setRefunding] = useState(false);
  const staff = getStaff();

  useEffect(() => { load(); }, [filter]);

  const load = async () => {
    setLoading(true);
    try { const r = await getOrders(filter || undefined); setItems(r.data?.items || []); } catch {} finally { setLoading(false); }
  };

  const openRefund = (order: any) => {
    setRefundOrder(order);
    setRefundAmount(0);
    setRefundReference('');
    setRefundReason('');
  };

  const submitRefund = async () => {
    if (!refundOrder || refundAmount <= 0 || !refundReason.trim()) return;
    setRefunding(true);
    try {
      await registerRefundNote(refundOrder.id, {
        ...buildRefundNotePayload({
          amountCents: refundAmount,
          reasonCode: refundReasonCode,
          responsibility: refundResponsibility,
          refundReference: refundReference.trim(),
          reason: refundReason.trim(),
        }),
        idempotency_key: makeIdempotencyKey('refund-note', refundOrder.id),
      });
      message.success('退款记录已登记');
      setRefundOrder(null);
      await load();
    } finally {
      setRefunding(false);
    }
  };

  return (
    <div>
      <Select
        value={filter} onChange={setFilter}
        style={{ width: 160, marginBottom: 16 }}
        options={[
          { value: '', label: '全部记录' },
          { value: 'pending_payment', label: '待门店确认' },
          { value: 'paid', label: '待核销' },
          { value: 'completed', label: '已完成' },
        ]}
      />
      {loading ? <Spin style={{ display: 'block', margin: '40px auto' }} /> :
       items.length === 0 ? <Empty description="暂无此类订单" /> :
       items.map((o: any) => (
        <Card key={o.id} size="small" style={{ marginBottom: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
            <span style={{ color: '#bbb', fontSize: 12 }}>{o.order_no}</span>
            <Tag color={STATUS_MAP[o.status]?.color}>{STATUS_MAP[o.status]?.text || o.status}</Tag>
          </div>
          <div style={{ fontWeight: 600 }}>{(o.items || []).map((i: any) => i.name + ' ×' + i.quantity).join('、') || '-'}</div>
          <div style={{ color: '#999', fontSize: 12 }}>预约 {o.booking_date || '-'} {o.booking_time || ''} · ¥{(o.pay_amount_cents / 100).toFixed(2)} · {o.created_at?.slice(5, 16)}</div>
          {o.refund_status && <Tag color={o.refund_status === 'refunded' ? 'red' : 'orange'}>{o.refund_status === 'refunded' ? '已全额退款' : '已部分退款'}</Tag>}
          {staff?.role === 'admin' && o.pay_status === 'paid' && <Button size="small" danger onClick={() => openRefund(o)}>登记退款</Button>}
        </Card>
      ))}
      <Modal
        title="登记已完成退款"
        open={Boolean(refundOrder)}
        onCancel={() => setRefundOrder(null)}
        onOk={() => void submitRefund()}
        okText="确认登记"
        cancelText="取消"
        confirmLoading={refunding}
        okButtonProps={{ danger: true, disabled: refundAmount <= 0 || !refundReason.trim() }}
      >
        <p>这里只登记线下或第三方渠道已经完成的退款，不会自动退回资金。</p>
        <InputNumber min={0.01} max={(refundOrder?.pay_amount_cents || 0) / 100} precision={2} value={refundAmount / 100} onChange={(value) => setRefundAmount(Math.round(Number(value || 0) * 100))} addonBefore="退款金额" addonAfter="元" style={{ width: '100%', marginBottom: 12 }} />
        <Select value={refundReasonCode} onChange={setRefundReasonCode} style={{ width: '100%', marginBottom: 12 }} options={[
          { label: '顾客投诉处理', value: 'customer_complaint' },
          { label: '服务项目未完成', value: 'service_incomplete' },
          { label: '重复收款', value: 'duplicate_payment' },
          { label: '价格纠错', value: 'pricing_correction' },
          { label: '其他', value: 'other' },
        ]} />
        <Select value={refundResponsibility} onChange={setRefundResponsibility} style={{ width: '100%', marginBottom: 12 }} options={[
          { label: '门店责任', value: 'store' },
          { label: '顾客原因', value: 'customer' },
          { label: '第三方原因', value: 'third_party' },
          { label: '双方协商', value: 'shared' },
        ]} />
        <Input value={refundReference} onChange={(event) => setRefundReference(event.target.value)} maxLength={64} placeholder="退款流水号或第三方凭证" style={{ marginBottom: 12 }} />
        <Input.TextArea value={refundReason} onChange={(event) => setRefundReason(event.target.value)} rows={3} maxLength={200} showCount placeholder="填写退款原因和现场处理" />
      </Modal>
    </div>
  );
}

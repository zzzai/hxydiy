import { useState, useEffect } from 'react';
import { Alert, Button, Card, Descriptions, Drawer, Empty, Input, InputNumber, List, Modal, Pagination, Select, Space, Spin, Tag, Typography, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { getOrderDetail, getOrderReconciliation, getOrders, getStaff, registerRefundNote } from '../api';
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
  const [reconOpen, setReconOpen] = useState(false);
  const [reconLoading, setReconLoading] = useState(false);
  const [recon, setRecon] = useState<any>();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detail, setDetail] = useState<any>();
  const staff = getStaff();

  const openReconciliation = async () => {
    setReconOpen(true); setRecon(undefined); setReconLoading(true);
    try { const response = await getOrderReconciliation(30); setRecon(response.data); }
    catch { message.error('对账检查失败，请稍后重试'); }
    finally { setReconLoading(false); }
  };

  useEffect(() => { void load(); }, [filter, page, pageSize]);

  const load = async () => {
    setLoading(true);
    try {
      const r = await getOrders({ status: filter || undefined, page, page_size: pageSize, q: search || undefined });
      setItems(r.data?.items || []);
      setTotal(r.data?.total || 0);
    } catch {} finally { setLoading(false); }
  };

  const openDetail = async (order: any) => {
    setDetailOpen(true); setDetail(undefined); setDetailLoading(true);
    try { const response = await getOrderDetail(order.id); setDetail(response.data); }
    catch { message.error('订单详情加载失败'); }
    finally { setDetailLoading(false); }
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
      <div className="page-heading">
        <div>
          <h2>结算记录</h2>
          <div className="page-kicker">查看本店结算状态并登记已完成的线下退款，不会自动退回资金</div>
        </div>
        <Space>
          <Button onClick={() => void openReconciliation()}>对账检查</Button>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>刷新</Button>
        </Space>
      </div>
      <div className="orders-filter-row">
        <span>记录状态</span>
        <Select
          aria-label="筛选结算记录状态"
          value={filter} onChange={(value) => { setFilter(value); setPage(1); }}
          style={{ width: 170 }}
          options={[
            { value: '', label: '全部记录' },
            { value: 'pending_payment', label: '待门店确认' },
            { value: 'paid', label: '待核销' },
            { value: 'confirmed', label: '已确认' },
            { value: 'checked_in', label: '已到店' },
            { value: 'in_service', label: '服务中' },
            { value: 'completed', label: '已完成' },
          ]}
        />
        <Input.Search
          aria-label="按订单号搜索"
          placeholder="搜索订单号"
          allowClear
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          onSearch={() => { setPage(1); void load(); }}
          style={{ width: 200 }}
        />
        <span className="orders-count">共 {total} 条</span>
      </div>
      {loading ? <Spin style={{ display: 'block', margin: '40px auto' }} /> :
       items.length === 0 ? <Empty description={filter ? '当前筛选下没有结算记录，可切换到全部记录查看' : '本店还没有结算记录'} /> :
       items.map((o: any) => (
        <Card key={o.id} size="small" style={{ marginBottom: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
            <Space size={6}>
              <span style={{ color: '#bbb', fontSize: 12 }}>{o.order_no}</span>
              {o.link_status === 'linked' && <Tag color="green">已关联选单</Tag>}
              {o.link_status === 'missing' && <Tag color="orange">未关联选单</Tag>}
            </Space>
            <Tag color={STATUS_MAP[o.status]?.color}>{STATUS_MAP[o.status]?.text || o.status}</Tag>
          </div>
          <div style={{ fontWeight: 600 }}>{(o.items || []).map((i: any) => i.name + ' ×' + i.quantity).join('、') || '-'}</div>
          <div style={{ color: '#999', fontSize: 12 }}>预约 {o.booking_date || '-'} {o.booking_time || ''} · ¥{(o.pay_amount_cents / 100).toFixed(2)} · {o.created_at?.slice(5, 16)}</div>
          {o.selection_session_id && <div style={{ color: '#667369', fontSize: 12 }}>选单 {o.selection_session_id.slice(0, 8)} · 选单金额 ¥{((o.selection_total_cents || 0) / 100).toFixed(2)}</div>}
          {o.refund_status && <Tag color={o.refund_status === 'refunded' ? 'red' : 'orange'}>{o.refund_status === 'refunded' ? '已全额退款' : '已部分退款'}</Tag>}
          <Space size={6}>
            <Button size="small" onClick={() => void openDetail(o)}>详情</Button>
            {staff?.role === 'admin' && o.pay_status === 'paid' && <Button size="small" danger onClick={() => openRefund(o)}>登记退款</Button>}
          </Space>
        </Card>
      ))}
      {total > 0 && <Pagination
        style={{ marginTop: 16, textAlign: 'right' }}
        current={page}
        pageSize={pageSize}
        total={total}
        showSizeChanger
        pageSizeOptions={[10, 20, 50]}
        onChange={(nextPage, nextSize) => { setPage(nextPage); if (nextSize !== pageSize) setPageSize(nextSize); }}
        showTotal={(value) => `共 ${value} 条`}
      />}
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
      <Modal title="选单与订单对账" open={reconOpen} onCancel={() => setReconOpen(false)} footer={<Button onClick={() => setReconOpen(false)}>关闭</Button>} width={760} loading={reconLoading}>
        {recon && <>
          <Alert
            type={recon.summary?.anomaly_count ? 'warning' : 'success'}
            showIcon
            message={recon.summary?.anomaly_count ? `发现 ${recon.summary.anomaly_count} 条待核对记录` : '近 30 天选单与订单未发现异常'}
            description={`检查订单 ${recon.summary?.orders_checked || 0} 条，选单 ${recon.summary?.selections_checked || 0} 条`}
            style={{ marginBottom: 12 }}
          />
          {recon.summary?.anomaly_count > 0 && <List
            size="small"
            dataSource={recon.items || []}
            renderItem={(item: any) => <List.Item>
              <Space direction="vertical" size={0}>
                <Space><Tag color={item.type === 'amount_mismatch' ? 'orange' : 'red'}>{item.type}</Tag><strong>{item.order_no || item.selection_session_id?.slice(0, 8)}</strong></Space>
                <span style={{ color: 'var(--hxy-text-secondary)' }}>{item.message}</span>
                {(item.order_id || item.selection_session_id) && <span style={{ color: 'var(--hxy-text-muted)', fontSize: 12 }}>订单 {item.order_id || '-'} · 选单 {item.selection_session_id || '-'}</span>}
              </Space>
            </List.Item>}
          />}
        </>}
      </Modal>
      <Drawer title="结算详情" width={520} open={detailOpen} onClose={() => setDetailOpen(false)} loading={detailLoading}>
        {detail?.order && <>
          <Descriptions column={1} size="small" items={[
            { label: '订单号', children: detail.order.order_no },
            { label: '状态', children: <Tag color={STATUS_MAP[detail.order.status]?.color}>{STATUS_MAP[detail.order.status]?.text || detail.order.status}</Tag> },
            { label: '实付', children: `¥${((detail.order.pay_amount_cents || 0) / 100).toFixed(2)}` },
            { label: '退款状态', children: detail.order.refund_status || '无' },
            { label: '预约', children: `${detail.order.booking_date || '-'} ${detail.order.booking_time || ''}` },
            { label: '选单', children: detail.order.selection_session_id ? `${detail.order.selection_session_id} · ¥${((detail.order.selection_total_cents || 0) / 100).toFixed(2)}` : '未关联' },
          ]} />
          <Typography.Title level={5}>服务项目</Typography.Title>
          <List size="small" dataSource={detail.order.items || []} locale={{ emptyText: '无项目快照' }} renderItem={(item: any) => <List.Item>{item.name || '项目'} × {item.quantity || 1}</List.Item>} />
          <Typography.Title level={5}>状态历史</Typography.Title>
          <List size="small" dataSource={detail.events || []} locale={{ emptyText: '暂无状态历史' }} renderItem={(event: any) => <List.Item><Space direction="vertical" size={0}><span>{event.from_status || '-'} → {event.to_status} · {event.action}</span><span style={{ color: 'var(--hxy-text-secondary)', fontSize: 12 }}>{event.created_at?.slice(0, 19).replace('T', ' ') || '-'} · {event.operator || '系统'}</span></Space></List.Item>} />
          <Typography.Title level={5}>退款调整</Typography.Title>
          <List size="small" dataSource={detail.refund_adjustments || []} locale={{ emptyText: '暂无退款调整' }} renderItem={(adjustment: any) => <List.Item><Space direction="vertical" size={0}><span>¥{(adjustment.amount_cents / 100).toFixed(2)} · {adjustment.reason_code}</span><span style={{ color: 'var(--hxy-text-secondary)', fontSize: 12 }}>{adjustment.created_at?.slice(0, 19).replace('T', ' ') || '-'} · {adjustment.reason || '无说明'}</span></Space></List.Item>} />
        </>}
      </Drawer>
    </div>
  );
}

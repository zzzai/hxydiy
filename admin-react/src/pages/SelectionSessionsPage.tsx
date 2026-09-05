import { useEffect, useState } from 'react';
import { App, Button, Card, Collapse, Descriptions, Drawer, Empty, Input, Segmented, Space, Table, Tag, Typography } from 'antd';
import { CheckOutlined, CloseOutlined, ReloadOutlined } from '@ant-design/icons';
import { approveSelectionChangeRequest, cancelSelectionSession, confirmSelectionSession, getCustomerProfileRecords, getSelectionChangeRequests, getSelectionSessions, rejectSelectionChangeRequest } from '../api';
import { canApproveSelectionChange, canRejectSelectionChange, selectionChangeItemSummary } from '../selectionChanges';
import { buildServiceReferenceDisplay } from '../serviceReferenceDisplay';

const STATUS: Record<string, { label: string; color: string }> = {
  submitted: { label: '待确认', color: 'processing' }, confirmed: { label: '已确认', color: 'success' },
  cancelled: { label: '已取消', color: 'default' }, expired: { label: '已过期', color: 'default' },
};
const sourceLabel = (source: string) => source === 'tablet' ? '门店平板' : source === 'mini_program' ? '顾客手机' : source || '门店端';
const itemSummary = (items: any[]) => (items || []).map((item) => `${item.name || `项目 ${item.project_id}`}${item.quantity > 1 ? ` ×${item.quantity}` : ''}`).join('、') || '未填写项目';
const dateText = (value?: string) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-';

export default function SelectionSessionsPage() {
  const { message, modal } = App.useApp();
  const [status, setStatus] = useState('submitted');
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<any | null>(null);
  const [changeRequests, setChangeRequests] = useState<any[]>([]);
  const [changeLoading, setChangeLoading] = useState(false);
  const [profileRecords, setProfileRecords] = useState<any[]>([]);
  const load = async () => {
    setLoading(true);
    try { const response = await getSelectionSessions(status === 'all' ? undefined : status); setItems(response.data?.items || []); }
    catch { message.error('选单加载失败'); }
    finally { setLoading(false); }
  };
  const loadChangeRequests = async () => {
    setChangeLoading(true);
    try { const response = await getSelectionChangeRequests(); setChangeRequests(response.data?.items || []); }
    catch { message.error('加选请求加载失败'); }
    finally { setChangeLoading(false); }
  };
  useEffect(() => { void load(); }, [status]);
  useEffect(() => { void loadChangeRequests(); }, []);
  useEffect(() => {
    if (!selected?.customer?.id) { setProfileRecords([]); return; }
    void getCustomerProfileRecords(selected.customer.id).then((response) => setProfileRecords(response.data?.items || [])).catch(() => setProfileRecords([]));
  }, [selected]);
  const act = (record: any, action: 'confirm' | 'cancel') => modal.confirm({
    title: action === 'confirm' ? '确认接收这份选单？' : '取消这份选单？',
    content: action === 'confirm' ? '确认后可按此需求继续安排服务，仍不创建订单。' : '取消后本次需求不再进入门店处理队列。',
    okText: action === 'confirm' ? '确认接收' : '取消选单', cancelText: '返回',
    okButtonProps: action === 'cancel' ? { danger: true } : undefined,
    onOk: async () => { try { await (action === 'confirm' ? confirmSelectionSession(record.id) : cancelSelectionSession(record.id)); message.success(action === 'confirm' ? '已确认服务项目' : '已取消服务选单'); setSelected(null); await load(); } catch { /* 全局请求拦截器已提示 */ } },
  });
  const approveChange = (request: any) => modal.confirm({
    title: '确认这次服务中加选？',
    content: '确认后新增项目会进入实际服务项；服务结束后系统会再次拒绝过期请求。',
    okText: '确认加选',
    cancelText: '返回',
    onOk: async () => {
      await approveSelectionChangeRequest(request.id);
      message.success('加选已确认并进入服务项');
      await loadChangeRequests();
    },
  });
  const rejectChange = (request: any) => {
    let reason = '';
    modal.confirm({
      title: '拒绝这次服务中加选？',
      content: <Input.TextArea autoFocus rows={3} maxLength={256} placeholder="填写拒绝原因" onChange={(event) => { reason = event.target.value; }} />,
      okText: '拒绝加选',
      cancelText: '返回',
      okButtonProps: { danger: true },
      onOk: async () => {
        if (!reason.trim()) {
          message.error('请填写拒绝原因');
          return Promise.reject(new Error('reason-required'));
        }
        await rejectSelectionChangeRequest(request.id, reason.trim());
        message.success('加选已拒绝');
        await loadChangeRequests();
      },
    });
  };
  return <Space direction="vertical" size={18} style={{ width: '100%' }}>
    <div className="page-heading"><div><Typography.Title level={3} style={{ margin: 0 }}>到店服务选单</Typography.Title><Typography.Text type="secondary">顾客先选服务与偏好，门店确认后再进入现场服务流程</Typography.Text></div><Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>刷新</Button></div>
    <Card><Segmented value={status} onChange={(value) => setStatus(String(value))} options={[{ label: '待确认', value: 'submitted' }, { label: '已确认', value: 'confirmed' }, { label: '已取消', value: 'cancelled' }, { label: '全部', value: 'all' }]} /></Card>
    <Card title="服务中追加项目" extra={<Button icon={<ReloadOutlined />} loading={changeLoading} onClick={() => void loadChangeRequests()}>刷新</Button>}>
      {!changeLoading && !changeRequests.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无待确认加选" /> : <Table rowKey="id" loading={changeLoading} dataSource={changeRequests} pagination={false} columns={[
        { title: '提交时间', dataIndex: 'created_at', width: 180, render: dateText },
        { title: '服务位来源', render: (_: unknown, record: any) => `${sourceLabel(record.selection?.source)} · ${record.selection?.device_label || '顾客设备'}` },
        { title: '新增项目', dataIndex: ['revision', 'added_items'], render: (value: any[]) => (value || []).map(selectionChangeItemSummary).join('、') || '无新增项目' },
        { title: '状态', dataIndex: 'state', width: 150, render: (value: string) => <Tag color="processing">{value === 'awaiting_staff_confirmation' ? '待确认' : value}</Tag> },
        { title: '操作', width: 210, render: (_: unknown, record: any) => canApproveSelectionChange(record.state) ? <Space size={6}><Button size="small" type="primary" icon={<CheckOutlined />} onClick={() => approveChange(record)}>确认加选</Button>{canRejectSelectionChange(record.state) && <Button size="small" danger icon={<CloseOutlined />} onClick={() => rejectChange(record)}>拒绝</Button>}</Space> : <Typography.Text type="secondary">已处理</Typography.Text> },
      ]} />}
    </Card>
    <Card>{!loading && !items.length ? <Empty description="暂无选单" /> : <Table rowKey="id" loading={loading} dataSource={items} pagination={{ pageSize: 20 }} onRow={(record) => ({ onClick: () => setSelected(record), style: { cursor: 'pointer' } })} columns={[
      { title: '提交时间', dataIndex: 'submitted_at', width: 180, render: dateText },
      { title: '顾客', dataIndex: 'customer', width: 170, render: (customer: any) => customer ? <Space size={4}><span>{customer.nickname || '已登录顾客'}</span>{customer.is_member && <Tag color="gold">会员</Tag>}</Space> : <Typography.Text type="secondary">未登录</Typography.Text> },
      { title: '来源', dataIndex: 'source', width: 130, render: (value: string, record: any) => <Tag>{sourceLabel(value)}{record.device_label ? ` · ${record.device_label}` : ''}</Tag> },
      { title: '服务需求', dataIndex: 'items', render: (value: any[]) => <Typography.Text ellipsis style={{ maxWidth: 380, display: 'inline-block' }}>{itemSummary(value)}</Typography.Text> },
      { title: '评价', dataIndex: 'feedback', width: 130, render: (feedback: any) => feedback ? <Space size={4}><Tag color="gold">{feedback.rating} 星</Tag><Typography.Text type="secondary">{feedback.tags?.length || 0} 项</Typography.Text></Space> : <Typography.Text type="secondary">未评价</Typography.Text> },
      { title: '状态', dataIndex: 'status', width: 90, render: (value: string) => <Tag color={STATUS[value]?.color}>{STATUS[value]?.label || value}</Tag> },
      { title: '操作', width: 190, render: (_: any, record: any) => record.status === 'submitted' ? <Space onClick={(event) => event.stopPropagation()}><Button size="small" type="primary" icon={<CheckOutlined />} onClick={() => act(record, 'confirm')}>确认选单</Button><Button size="small" danger icon={<CloseOutlined />} onClick={() => act(record, 'cancel')}>取消</Button></Space> : <Typography.Text type="secondary">查看详情</Typography.Text> },
    ]} />}</Card>
    <Drawer title="选单详情" open={Boolean(selected)} onClose={() => setSelected(null)} width={420}>{selected && <Space direction="vertical" size={18} style={{ width: '100%' }}>
      <Descriptions column={1} size="small" items={[{ label: '状态', children: <Tag color={STATUS[selected.status]?.color}>{STATUS[selected.status]?.label || selected.status}</Tag> }, { label: '顾客', children: selected.customer ? `${selected.customer.nickname || '已登录顾客'} · ${selected.customer.phone}` : '匿名访客，尚未登录' }, { label: '会员身份', children: selected.customer?.is_member ? <Tag color="gold">会员</Tag> : selected.customer ? '非会员' : '-' }, { label: '来源', children: sourceLabel(selected.source) }, { label: '设备', children: selected.device_label || '-' }, { label: '提交时间', children: dateText(selected.submitted_at) }]} />
      <div><Typography.Text strong>项目</Typography.Text><Typography.Paragraph style={{ marginTop: 8 }}>{itemSummary(selected.items)}</Typography.Paragraph></div>
      <Descriptions column={1} size="small" items={[
        { label: '计价档位', children: selected.pricing_snapshot?.applied_price_type === 'member' ? <Tag color="gold">会员价</Tag> : selected.pricing_snapshot?.applied_price_type === 'group' ? <Tag color="blue">团购价</Tag> : <Tag>门店价</Tag> },
        { label: selected.status === 'confirmed' ? '已确认金额' : '当前预计金额', children: `¥${((selected.pricing_snapshot?.payable_total_cents ?? selected.store_total_cents ?? 0) / 100).toFixed(1)}` },
        ...(selected.pricing_snapshot?.promotion_adjustment_cents ? [{ label: '组合优惠', children: `-¥${Math.abs(selected.pricing_snapshot.promotion_adjustment_cents / 100).toFixed(1)}` }] : []),
      ]} />
      <div><Typography.Text strong>DIY 需求</Typography.Text><Typography.Paragraph style={{ marginTop: 8 }}>{(selected.items || []).flatMap((item: any) => item.diy_preferences || []).join('、') || '未填写'}</Typography.Paragraph></div>
      <div><Typography.Text strong>服务评价</Typography.Text>{selected.feedback ? <Descriptions column={1} size="small" style={{ marginTop: 8 }} items={[{ label: '评分', children: <Tag color="gold">{selected.feedback.rating} 星</Tag> }, { label: '标签', children: selected.feedback.tags?.join('、') || '未选择标签' }, { label: '反馈', children: selected.feedback.note || '未填写文字反馈' }, { label: '时间', children: dateText(selected.feedback.created_at) }]} /> : <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>服务完成后，顾客评价会显示在这里。</Typography.Paragraph>}</div>
      {selected.customer && <Card size="small" title="服务参考（只读）">
        <Typography.Paragraph type="secondary" style={{ marginBottom: 8 }}>仅作到店服务参考，不构成医疗建议；结构化记录不会转为普通运营标签。</Typography.Paragraph>
        {profileRecords.length ? profileRecords.slice(0, 5).map((record: any) => {
          const display = buildServiceReferenceDisplay(record);
          const isStructured = Boolean(display.version);
          return <div key={record.id} style={{ marginBottom: 12, paddingBottom: 10, borderBottom: '1px solid #f0f0f0' }}>
            {isStructured ? <>
              <Space wrap size={[4, 4]}><Tag color="green">{display.version}</Tag><Tag color={record.customer_confirmed ? 'success' : 'default'}>{record.customer_confirmed ? '顾客已确认' : '本次观察，未确认'}</Tag></Space>
              {display.groups.map(group => <div key={group.title} style={{ marginTop: 8 }}><Typography.Text strong>{group.title}</Typography.Text><Descriptions column={1} size="small" items={group.items.map(item => ({ label: item.label, children: item.value }))} /></div>)}
              {display.collapsedQuote && <Collapse size="small" ghost items={[{ key: 'quote', label: '查看相关情况原话（服务前须再次确认）', children: <Typography.Paragraph>{display.collapsedQuote}</Typography.Paragraph> }]} />}
            </> : <><Space wrap size={[4, 4]}>{Object.values(record.profile || {}).filter(value => typeof value === 'string' && value).map((value: any) => <Tag key={String(value)} color="blue">{String(value)}</Tag>)}{(record.signals || []).map((signal: string) => <Tag key={signal}>{signal}</Tag>)}</Space>{record.note && <Typography.Paragraph style={{ margin: '4px 0 0' }}>{record.note}</Typography.Paragraph>}</>}
            <Typography.Text type="secondary" style={{ display: 'block', marginTop: 6 }}>{dateText(record.created_at)} · {record.created_by_name || '技师'} · 来源：{record.source || '-'}{record.customer_confirmed && record.confirmed_at ? ` · 确认于 ${dateText(record.confirmed_at)}` : ''}</Typography.Text>
          </div>;
        }) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无服务参考" />}
      </Card>}
      {selected.status === 'submitted' && <Space><Button type="primary" icon={<CheckOutlined />} onClick={() => act(selected, 'confirm')}>确认服务项目</Button><Button danger icon={<CloseOutlined />} onClick={() => act(selected, 'cancel')}>取消服务选单</Button></Space>}
    </Space>}</Drawer>
  </Space>;
}

import { useCallback, useEffect, useMemo, useState } from 'react';
import { App, Button, Col, Empty, Popconfirm, Result, Row, Space, Spin, Statistic, Table, Tag, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { finishService, getTodayStats, readyService } from '../api';
import { dataProvider } from '../core/dataProvider';
import { resources } from '../core/resources';
import { getNextOperation, getOperationConfirmation, getResourceStatus, type LiveBoard, type LiveVisit, makeIdempotencyKey, type OperationAction } from '../operations';

const { Text, Title } = Typography;
const emptyBoard: LiveBoard = { summary: {}, visits: [], resources: { technicians: [], rooms: [] } };
const sectionStyle: React.CSSProperties = { background: '#fff', border: '1px solid #edf0ee', borderRadius: 6, padding: 20 };
const itemNames = (items: LiveVisit['items']) => items.map((item) => `${item.name || '服务项目'}${item.quantity ? ` ×${item.quantity}` : ''}`).join('、');

function boardFromResponse(value: unknown): LiveBoard {
  if (!value || typeof value !== 'object') return emptyBoard;
  const payload = 'data' in value && value.data && typeof value.data === 'object' ? value.data : value;
  if (!payload || typeof payload !== 'object' || !Array.isArray((payload as { visits?: unknown }).visits)) return emptyBoard;
  return { ...emptyBoard, ...(payload as Partial<LiveBoard>) };
}

export default function TodayPage() {
  const { message } = App.useApp();
  const [stats, setStats] = useState<Record<string, number>>({});
  const [board, setBoard] = useState<LiveBoard>(emptyBoard);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [acting, setActing] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      dataProvider.invalidate(resources.serviceOrders);
      const [statsResponse, boardResponse] = await Promise.all([
        getTodayStats(),
        dataProvider.getList<unknown>(resources.serviceOrders),
      ]);
      setStats(statsResponse.data || {});
      setBoard(boardFromResponse(boardResponse));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '请稍后重试');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const run = async (key: string, request: () => Promise<unknown>, success: string) => {
    setActing(key);
    try { await request(); message.success(success); await load(); } finally { setActing(''); }
  };

  const runServiceAction = (visit: LiveVisit, action: OperationAction) => {
    const id = visit.service_order_id;
    const key = makeIdempotencyKey(action, id);
    const requests: Record<OperationAction, () => Promise<unknown>> = {
      ready: () => readyService(id, key), finish: () => finishService(id, key),
    };
    const success: Record<OperationAction, string> = {
      ready: '已确认服务', finish: '已记录服务结束',
    };
    return run(`${action}-${id}`, requests[action], success[action]);
  };

  const columns = useMemo(() => [
    { title: '顾客服务', key: 'service', render: (_: unknown, record: LiveVisit) => <Space direction="vertical" size={1}><Text strong>{itemNames(record.items) || '到店服务'}</Text><Text type="secondary" style={{ fontSize: 12 }}>{record.order_no}</Text></Space> },
    { title: '进度', dataIndex: 'status', width: 110 },
    { title: '技师 / 资源', key: 'resource', width: 180, render: (_: unknown, record: LiveVisit) => record.technician_name ? `${record.technician_name} · ${record.room_name}` : <Text type="secondary">等待智慧宝现场安排</Text> },
    { title: '金额', dataIndex: 'pay_amount_cents', width: 100, align: 'right' as const, render: (amount: number) => `¥${(amount / 100).toFixed(2)}` },
    { title: '下一步', key: 'action', width: 130, align: 'right' as const, render: (_: unknown, record: LiveVisit) => { const next = getNextOperation(record.status, record.service_order_status); if (!next) return <Text type="secondary">等待处理</Text>; return <Popconfirm title={getOperationConfirmation(next.label)} onConfirm={() => runServiceAction(record, next.action)}><Button loading={acting === `${next.action}-${record.service_order_id}`}>{next.label}</Button></Popconfirm>; } },
  ], [acting]);

  if (error) return <Result status="error" title="今日运营数据加载失败" subTitle={error} extra={<Button type="primary" icon={<ReloadOutlined />} onClick={() => void load()}>重试</Button>} />;

  return <Space direction="vertical" size={16} style={{ width: '100%' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}><div><Title level={3} style={{ margin: 0 }}>今日运营</Title><Text type="secondary">在店服务与结算实时状态</Text></div><Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>刷新</Button></div>
    <Row gutter={[12, 12]}>{[['服务中', board.summary.in_service || 0], ['待结账', board.summary.pending_checkout || 0], ['今日实收', `¥${((stats.paid_amount_cents || 0) / 100).toFixed(0)}`]].map(([label, value]) => <Col xs={12} md={8} key={String(label)}><div style={{ ...sectionStyle, padding: '16px 18px' }}><Statistic title={label} value={value} /></div></Col>)}</Row>
    <section style={sectionStyle}><Text strong style={{ fontSize: 16 }}>在店服务流</Text>{loading ? <Spin style={{ display: 'block', margin: '32px auto' }} /> : <Table<LiveVisit> rowKey="id" columns={columns} dataSource={board.visits} pagination={false} locale={{ emptyText: <Empty description="当前没有在店服务" /> }} scroll={{ x: 760 }} />}</section>
    <section style={sectionStyle}><Text strong style={{ fontSize: 16 }}>资源状态</Text><Row gutter={[12, 12]} style={{ marginTop: 12 }}><Col span={24}><Text type="secondary">技师</Text><div>{board.resources.technicians.map((item) => <Tag key={item.id} color={getResourceStatus(item.status).color}>{item.name} · {getResourceStatus(item.status).text}</Tag>)}</div></Col><Col span={24}><Text type="secondary">房间 / 沙发</Text><div>{board.resources.rooms.map((item) => <Tag key={item.id} color={getResourceStatus(item.status).color}>{item.name} · {getResourceStatus(item.status).text}</Tag>)}</div></Col></Row></section>
  </Space>;
}

import { useEffect, useState } from 'react';
import { PageContainer } from '@ant-design/pro-components';
import { Alert, Button, Card, Col, DatePicker, Empty, Row, Space, Statistic, Table, Tag, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
import { getBrandOverview } from '../api';

type StoreOverview = {
  store_id: number;
  store_code: string;
  name: string;
  city: string;
  status: string;
  paid_order_count: number;
  paid_amount_cents: number;
  customer_count: number;
  review_count: number;
  average_rating: number | null;
  low_rating_count: number;
};

type Overview = {
  period: { start_date: string; end_date: string; timezone: string };
  summary: {
    store_count: number;
    open_store_count: number;
    paid_order_count: number;
    paid_amount_cents: number;
    average_order_value_cents: number | null;
    review_count: number;
    average_rating: number | null;
    low_rating_count: number;
  };
  stores: StoreOverview[];
  generated_at: string;
};

const statusLabels: Record<string, string> = {
  preparing: '筹备中',
  trial_open: '试营业',
  open: '营业中',
  suspended: '暂停营业',
  closed: '已停业',
};

const statusColors: Record<string, string> = {
  preparing: 'gold',
  trial_open: 'green',
  open: 'green',
  suspended: 'orange',
  closed: 'default',
};

function money(cents?: number | null) {
  if (cents === null || cents === undefined) return '—';
  return `¥${(cents / 100).toFixed(2)}`;
}

function ratio(value?: number | null) {
  return value === null || value === undefined ? '—' : value.toFixed(2);
}

export default function BrandOverviewPage() {
  const [range, setRange] = useState<[Dayjs, Dayjs]>([dayjs().subtract(6, 'day'), dayjs()]);
  const [data, setData] = useState<Overview>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = async (next = range) => {
    setLoading(true);
    setError('');
    try {
      const response = await getBrandOverview(next[0].format('YYYY-MM-DD'), next[1].format('YYYY-MM-DD'));
      setData(response.data);
    } catch {
      setData(undefined);
      setError('品牌经营数据加载失败，请稍后重试。');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const stores = data?.stores || [];
  const summary = data?.summary;

  return (
    <PageContainer
      title="品牌总览"
      content="跨门店经营汇总 · 按上海自然日统计；实收只统计已支付且未取消的订单。"
      extra={[
        <DatePicker.RangePicker
          key="range"
          value={range}
          allowClear={false}
          onChange={(values) => {
            if (!values?.[0] || !values[1]) return;
            const next: [Dayjs, Dayjs] = [values[0], values[1]];
            setRange(next);
            void load(next);
          }}
        />,
        <Button key="refresh" icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>刷新</Button>,
      ]}
    >
      {error && <Alert type="error" showIcon message={error} action={<Button size="small" onClick={() => void load()}>重试</Button>} style={{ marginBottom: 16 }} />}
      {!error && !data && !loading && <Empty description="暂无品牌经营数据" />}
      {summary && <>
        <Row gutter={[12, 12]}>
          <Col xs={12} md={8} xl={4}><Card><Statistic title="门店数" value={summary.store_count} suffix={`/ ${summary.open_store_count} 营业`} /></Card></Col>
          <Col xs={12} md={8} xl={4}><Card><Statistic title="实收金额" value={summary.paid_amount_cents / 100} precision={2} prefix="¥" /></Card></Col>
          <Col xs={12} md={8} xl={4}><Card><Statistic title="有效订单" value={summary.paid_order_count} /></Card></Col>
          <Col xs={12} md={8} xl={4}><Card><Statistic title="客单价" value={summary.average_order_value_cents ? summary.average_order_value_cents / 100 : 0} precision={2} prefix="¥" /></Card></Col>
          <Col xs={12} md={8} xl={4}><Card><Statistic title="评价数" value={summary.review_count} suffix={summary.average_rating === null ? '' : `均分 ${ratio(summary.average_rating)}`} /></Card></Col>
          <Col xs={12} md={8} xl={4}><Card><Statistic title="低分待跟进" value={summary.low_rating_count} valueStyle={summary.low_rating_count > 0 ? { color: 'var(--hxy-warning)' } : undefined} /></Card></Col>
        </Row>
        <Card style={{ marginTop: 16 }}>
          <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 12 }}>
            <Typography.Text strong>门店经营明细</Typography.Text>
            <Typography.Text type="secondary">更新于 {data?.generated_at ? dayjs(data.generated_at).format('YYYY-MM-DD HH:mm') : '—'}</Typography.Text>
          </Space>
          <Table<StoreOverview>
            rowKey="store_id"
            loading={loading}
            dataSource={stores}
            pagination={false}
            scroll={{ x: 900 }}
            locale={{ emptyText: <Empty description="所选日期暂无门店数据" /> }}
            columns={[
              { title: '门店', dataIndex: 'name', render: (value, row) => <Space direction="vertical" size={0}><Typography.Text strong>{value}</Typography.Text><Typography.Text type="secondary">{row.store_code}</Typography.Text></Space> },
              { title: '城市', dataIndex: 'city', width: 110 },
              { title: '状态', dataIndex: 'status', width: 100, render: (value) => <Tag color={statusColors[value]}>{statusLabels[value] || value}</Tag> },
              { title: '实收金额', dataIndex: 'paid_amount_cents', width: 130, align: 'right', render: (value) => money(value) },
              { title: '有效订单', dataIndex: 'paid_order_count', width: 100, align: 'right' },
              { title: '顾客数', dataIndex: 'customer_count', width: 100, align: 'right' },
              { title: '评价数', dataIndex: 'review_count', width: 90, align: 'right' },
              { title: '均分', dataIndex: 'average_rating', width: 80, align: 'right', render: (value) => ratio(value) },
              { title: '低分', dataIndex: 'low_rating_count', width: 80, align: 'right', render: (value) => <span style={{ color: value > 0 ? 'var(--hxy-warning)' : undefined }}>{value}</span> },
            ]}
          />
        </Card>
      </>}
    </PageContainer>
  );
}

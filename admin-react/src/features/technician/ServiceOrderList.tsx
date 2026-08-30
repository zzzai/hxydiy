import { useEffect, useState } from 'react';
import { Alert, Button, Empty, Pagination, Select, Space, Spin, Table, Tag, Typography } from 'antd';
import { dataProvider } from '../../core/dataProvider';
import { resources } from '../../core/resources';

type ServiceOrderListProps = {
  defaultStatus?: 'in_progress' | 'history';
  pageSize?: number;
  onCreateProfile?: (customerId: number) => void;
};

export default function ServiceOrderList({ defaultStatus = 'in_progress', pageSize = 30, onCreateProfile }: ServiceOrderListProps) {
  const [status, setStatus] = useState<'in_progress' | 'history'>(defaultStatus);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError('');
    dataProvider.getList<any>(resources.technicianServiceOrders, { status, page, page_size: pageSize })
      .then((payload) => {
        if (!mounted) return;
        setData(payload?.items || []);
        setTotal(payload?.total || 0);
      })
      .catch(() => mounted && setError('服务单加载失败，请稍后重试'))
      .finally(() => mounted && setLoading(false));
    return () => { mounted = false; };
  }, [status, page, pageSize]);

  return (
    <section aria-label="服务单列表">
      <Space style={{ marginBottom: 16 }}>
        <Typography.Text strong>服务单</Typography.Text>
        <Select
          value={status}
          onChange={(value) => { setStatus(value); setPage(1); }}
          options={[{ value: 'in_progress', label: '进行中' }, { value: 'history', label: '历史记录' }]}
          aria-label="服务单状态"
        />
      </Space>
      {error && <Alert type="error" showIcon message={error} />}
      {loading ? <Spin /> : data.length === 0 ? <Empty description="暂无服务单" /> : <>
        <Table
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={data}
          columns={[
            { title: '服务单', dataIndex: 'id', width: 90, render: (id: number) => `#${id}` },
            { title: '顾客', dataIndex: ['customer', 'nickname'], render: (_: string, row: any) => <Space direction="vertical" size={0}><span>{row.customer?.nickname || '顾客'}</span><Typography.Text type="secondary">{row.customer?.phone_masked || '****'}</Typography.Text></Space> },
            { title: '服务项目', dataIndex: 'items', render: (items: any[]) => (items || []).map((item) => item.name).filter(Boolean).join('、') || '服务项目' },
            { title: '状态', dataIndex: 'status', render: (value: string) => <Tag>{value === 'completed' ? '已完成' : value === 'cancelled' ? '已取消' : '进行中'}</Tag> },
            { title: '创建时间', dataIndex: 'created_at', render: (value: string | null) => value?.slice(0, 16).replace('T', ' ') || '—' },
            ...(onCreateProfile ? [{ title: '记录', key: 'profile', width: 100, render: (_: unknown, row: any) => row.customer?.id ? <Button size="small" onClick={() => onCreateProfile(row.customer.id)}>画像</Button> : null }] : []),
          ]}
        />
        <Pagination style={{ marginTop: 16 }} current={page} pageSize={pageSize} total={total} showSizeChanger={false} onChange={setPage} />
      </>}
    </section>
  );
}

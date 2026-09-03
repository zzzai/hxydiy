import { useEffect, useState } from 'react';
import { Button, Card, DatePicker, Empty, Input, Space, Spin, Table, Tag, message } from 'antd';
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { exportAuditLogs, getAuditLogs } from '../api';

const initialRange: [Dayjs, Dayjs] = [dayjs().subtract(6, 'day'), dayjs()];

type AuditRow = {
  id: number;
  created_at: string | null;
  actor_type: string;
  actor_id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  detail: Record<string, unknown>;
};

export default function AuditLogsPage() {
  const [range, setRange] = useState<[Dayjs, Dayjs]>(initialRange);
  const [action, setAction] = useState('');
  const [employeeId, setEmployeeId] = useState('');
  const [data, setData] = useState<{ items: AuditRow[]; total: number; page: number; page_size: number }>({ items: [], total: 0, page: 1, page_size: 20 });
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  const query = (nextPage = page) => ({
    start_date: range[0].format('YYYY-MM-DD'),
    end_date: range[1].format('YYYY-MM-DD'),
    action: action || undefined,
    employee_id: employeeId || undefined,
    page: nextPage,
    page_size: 20,
  });

  const load = async (nextPage = page) => {
    setLoading(true);
    try {
      const response = await getAuditLogs(query(nextPage));
      setData(response.data);
      setPage(nextPage);
    } catch {} finally { setLoading(false); }
  };

  useEffect(() => { load(1); }, []);

  const download = async () => {
    try {
      const response = await exportAuditLogs(query(1));
      const url = URL.createObjectURL(response.data);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'audit-logs.csv';
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      message.error('导出失败');
    }
  };

  if (loading && !data.items.length) return <Spin style={{ display: 'block', margin: '40px auto' }} />;

  return (
    <div>
      <div className="page-heading">
        <div><h2>审计日志</h2><div className="page-kicker">仅展示当前权限范围内的脱敏操作记录</div></div>
        <Space wrap>
          <DatePicker.RangePicker value={range} allowClear={false} format="YYYY-MM-DD" onChange={(value) => value?.[0] && value?.[1] && setRange([value[0], value[1]])} />
          <Input placeholder="动作类型" value={action} onChange={(event) => setAction(event.target.value)} allowClear style={{ width: 150 }} />
          <Input placeholder="员工 ID" value={employeeId} onChange={(event) => setEmployeeId(event.target.value)} allowClear style={{ width: 110 }} />
          <Button type="primary" icon={<ReloadOutlined />} onClick={() => load(1)}>查询</Button>
          <Button icon={<DownloadOutlined />} onClick={download}>导出 CSV</Button>
        </Space>
      </div>
      <Card>
        <Table
          rowKey="id"
          size="small"
          loading={loading}
          dataSource={data.items}
          locale={{ emptyText: <Empty description="暂无审计记录" /> }}
          pagination={{ current: data.page, pageSize: data.page_size, total: data.total, showSizeChanger: false, onChange: (next) => load(next) }}
          scroll={{ x: 960 }}
          columns={[
            { title: '时间', dataIndex: 'created_at', width: 180, render: (value: string | null) => value ? new Date(value).toLocaleString('zh-CN') : '-' },
            { title: '动作', dataIndex: 'action', width: 190, render: (value: string) => <Tag color="blue">{value}</Tag> },
            { title: '操作者', dataIndex: 'actor_id', width: 90 },
            { title: '对象', width: 160, render: (_: unknown, row: AuditRow) => `${row.entity_type} #${row.entity_id}` },
            { title: '详情', dataIndex: 'detail', render: (value: Record<string, unknown>) => <pre style={{ maxWidth: 420, margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 12 }}>{JSON.stringify(value)}</pre> },
          ]}
        />
      </Card>
    </div>
  );
}

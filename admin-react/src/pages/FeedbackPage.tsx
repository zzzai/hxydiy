import { useEffect, useState } from 'react';
import { Button, Card, Empty, Input, Select, Space, Spin, Table, Tag, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { getFeedback, updateFeedbackFollowUp } from '../api';

type FeedbackRow = {
  id: number;
  selection_session_id: string;
  rating: number;
  tags: string[];
  note: string;
  follow_up_status: 'open' | 'in_progress' | 'resolved' | 'dismissed';
  follow_up_staff_id: number | null;
  follow_up_note: string;
  followed_up_at: string | null;
  created_at: string | null;
};

const statusText: Record<string, string> = { open: '待跟进', in_progress: '处理中', resolved: '已解决', dismissed: '已忽略' };

export default function FeedbackPage() {
  const [rows, setRows] = useState<FeedbackRow[]>([]);
  const [status, setStatus] = useState('open');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const response = await getFeedback({ low_rating_only: true, follow_up_status: status, page: 1, page_size: 100 });
      setRows(response.data.items);
    } catch {} finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [status]);

  const update = async (row: FeedbackRow, nextStatus: string, note: string) => {
    try {
      await updateFeedbackFollowUp(row.id, { follow_up_status: nextStatus, follow_up_note: note });
      message.success('跟进状态已更新');
      load();
    } catch {}
  };

  if (loading && !rows.length) return <Spin style={{ display: 'block', margin: '40px auto' }} />;

  return (
    <div>
      <div className="page-heading">
        <div><h2>低分评价跟进</h2><div className="page-kicker">评分 1-2 星进入待跟进队列，处理动作会记录审计日志</div></div>
        <Space>
          <Select value={status} onChange={setStatus} options={Object.entries(statusText).map(([value, label]) => ({ value, label }))} style={{ width: 120 }} />
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        </Space>
      </div>
      <Card>
        <Table
          rowKey="id"
          size="small"
          loading={loading}
          dataSource={rows}
          locale={{ emptyText: <Empty description="暂无待跟进评价" /> }}
          pagination={false}
          scroll={{ x: 980 }}
          columns={[
            { title: '时间', dataIndex: 'created_at', width: 170, render: (value: string | null) => value ? new Date(value).toLocaleString('zh-CN') : '-' },
            { title: '评分', dataIndex: 'rating', width: 70, render: (value: number) => <Tag color="red">{value} 星</Tag> },
            { title: '标签', dataIndex: 'tags', width: 150, render: (value: string[]) => value?.join('、') || '-' },
            { title: '顾客备注', dataIndex: 'note', width: 240 },
            { title: '处理备注', dataIndex: 'follow_up_note', width: 240, render: (value: string, row: FeedbackRow) => <Input.TextArea defaultValue={value} autoSize={{ minRows: 1, maxRows: 3 }} onBlur={(event) => event.target.value !== value && update(row, row.follow_up_status, event.target.value)} /> },
            { title: '状态', dataIndex: 'follow_up_status', width: 120, render: (value: string, row: FeedbackRow) => <Select value={value} onChange={(next) => update(row, next, row.follow_up_note)} options={Object.entries(statusText).map(([option, label]) => ({ value: option, label }))} style={{ width: 105 }} /> },
          ]}
        />
      </Card>
    </div>
  );
}

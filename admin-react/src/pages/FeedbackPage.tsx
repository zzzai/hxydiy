import { useEffect, useState } from 'react';
import { Button, Card, Descriptions, Drawer, Empty, Input, Select, Space, Spin, Table, Tag, Typography, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { getFeedback, getFeedbackDetail, updateFeedbackFollowUp } from '../api';
import { feedbackSourceLabel, feedbackTypeLabel, feedbackUsesServiceLink, type FeedbackType } from './feedback-page-model';

type FeedbackRow = {
  id: number;
  feedback_type: FeedbackType;
  selection_session_id: string | null;
  rating: number;
  tags: string[];
  note: string;
  source: string;
  follow_up_status: 'open' | 'in_progress' | 'resolved' | 'dismissed';
  follow_up_staff_id: number | null;
  follow_up_note: string;
  followed_up_at: string | null;
  created_at: string | null;
};

const statusText: Record<string, string> = { open: '待跟进', in_progress: '处理中', resolved: '已解决', dismissed: '已忽略' };
const typeOptions = [{ value: 'all', label: '全部反馈' }, { value: 'visit_feedback', label: '到店反馈' }, { value: 'service_review', label: '服务评价' }];

export default function FeedbackPage() {
  const [rows, setRows] = useState<FeedbackRow[]>([]);
  const [status, setStatus] = useState('open');
  const [type, setType] = useState<'all' | FeedbackType>('all');
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<FeedbackRow | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const response = await getFeedback({ follow_up_status: status, feedback_type: type === 'all' ? undefined : type, page: 1, page_size: 100 });
      setRows(response.data.items);
    } catch {} finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [status, type]);

  const openDetail = async (row: FeedbackRow) => {
    try { setSelected((await getFeedbackDetail(row.feedback_type, row.id)).data); } catch {}
  };
  const update = async (row: FeedbackRow, nextStatus: string, note: string) => {
    try {
      const response = await updateFeedbackFollowUp(row.feedback_type, row.id, { follow_up_status: nextStatus, follow_up_note: note });
      message.success('处理状态已更新');
      if (selected?.id === row.id && selected.feedback_type === row.feedback_type) setSelected(response.data);
      load();
    } catch {}
  };

  if (loading && !rows.length) return <Spin style={{ display: 'block', margin: '40px auto' }} />;

  return <div>
    <div className="page-heading">
      <div><h2>顾客反馈</h2><div className="page-kicker">到店反馈与已完成服务评价分开标识，处理动作会记录审计日志</div></div>
      <Space>
        <Select value={type} onChange={setType} options={typeOptions} style={{ width: 120 }} />
        <Select value={status} onChange={setStatus} options={Object.entries(statusText).map(([value, label]) => ({ value, label }))} style={{ width: 120 }} />
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
      </Space>
    </div>
    <Card>
      <Table rowKey={(row) => `${row.feedback_type}-${row.id}`} size="small" loading={loading} dataSource={rows}
        locale={{ emptyText: <Empty description="暂无符合条件的反馈" /> }} pagination={false} scroll={{ x: 1050 }}
        onRow={(row) => ({ onClick: () => openDetail(row) })}
        columns={[
          { title: '时间', dataIndex: 'created_at', width: 170, render: (value: string | null) => value ? new Date(value).toLocaleString('zh-CN') : '-' },
          { title: '类型', width: 100, render: (_: unknown, row: FeedbackRow) => <Tag color={row.feedback_type === 'visit_feedback' ? 'green' : 'blue'}>{feedbackTypeLabel(row.feedback_type)}</Tag> },
          { title: '来源', width: 120, render: (_: unknown, row: FeedbackRow) => feedbackSourceLabel(row) },
          { title: '评分', dataIndex: 'rating', width: 70, render: (value: number) => <Tag color={value <= 2 ? 'red' : 'gold'}>{value} 星</Tag> },
          { title: '标签', dataIndex: 'tags', width: 180, render: (value: string[]) => value?.join('、') || '-' },
          { title: '顾客反馈', dataIndex: 'note', ellipsis: true },
          { title: '状态', dataIndex: 'follow_up_status', width: 100, render: (value: string) => statusText[value] || value },
        ]} />
    </Card>
    <Drawer title={selected ? `${feedbackTypeLabel(selected.feedback_type)}详情` : '反馈详情'} width={520} open={Boolean(selected)} onClose={() => setSelected(null)}>
      {selected && <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Descriptions column={1} size="small" items={[
          { label: '类型', children: feedbackTypeLabel(selected.feedback_type) },
          { label: '来源', children: feedbackSourceLabel(selected) },
          { label: '评分', children: `${selected.rating} 星` },
          { label: '标签', children: selected.tags.join('、') || '未选择标签' },
          { label: '反馈内容', children: selected.note || '未填写文字反馈' },
          { label: '提交时间', children: selected.created_at ? new Date(selected.created_at).toLocaleString('zh-CN') : '-' },
          ...(feedbackUsesServiceLink(selected) ? [{ label: '关联服务', children: selected.selection_session_id }] : []),
        ]} />
        {selected.feedback_type === 'visit_feedback' && <Typography.Text type="secondary">此反馈未关联服务单或技师，不纳入技师评分。</Typography.Text>}
        <Select value={selected.follow_up_status} onChange={(next) => update(selected, next, selected.follow_up_note)} options={Object.entries(statusText).map(([value, label]) => ({ value, label }))} style={{ width: '100%' }} />
        <Input.TextArea value={selected.follow_up_note} maxLength={1000} autoSize={{ minRows: 3, maxRows: 8 }} onChange={(event) => setSelected({ ...selected, follow_up_note: event.target.value })} placeholder="记录处理结果，不填写无关顾客隐私" />
        <Button type="primary" onClick={() => update(selected, selected.follow_up_status, selected.follow_up_note)}>保存处理记录</Button>
      </Space>}
    </Drawer>
  </div>;
}

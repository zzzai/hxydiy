import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Descriptions, Drawer, Empty, Input, Select, Space, Spin, Table, Tag, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { getFeedback, getFeedbackDetail, updateFeedbackFollowUp } from '../api';
import { feedbackSourceLabel, feedbackTypeLabel, feedbackUsesServiceLink, type FeedbackType } from './feedback-page-model';
import './daily-operations.css';

type FeedbackRow = {
  id: number; feedback_type: FeedbackType; selection_session_id: string | null;
  rating: number; tags: string[]; note: string; source: string;
  follow_up_status: 'open' | 'in_progress' | 'resolved' | 'dismissed';
  follow_up_staff_id: number | null; follow_up_note: string;
  followed_up_at: string | null; created_at: string | null;
};
const statusText: Record<string, string> = { open: '待跟进', in_progress: '处理中', resolved: '已解决', dismissed: '无需跟进' };
const typeOptions = [{ value: 'all', label: '全部反馈' }, { value: 'visit_feedback', label: '到店反馈' }, { value: 'service_review', label: '服务评价' }];

export default function FeedbackPage() {
  const { message, modal } = App.useApp();
  const [rows, setRows] = useState<FeedbackRow[]>([]);
  const [status, setStatus] = useState('open');
  const [type, setType] = useState<'all' | FeedbackType>('all');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [target, setTarget] = useState<FeedbackRow | null>(null);
  const [selected, setSelected] = useState<FeedbackRow | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [draftStatus, setDraftStatus] = useState('open');
  const [draftNote, setDraftNote] = useState('');
  const [saving, setSaving] = useState(false);
  const listVersion = useRef(0);
  const detailVersion = useRef(0);
  const savingRef = useRef(false);
  const dirty = !!selected && (draftStatus !== selected.follow_up_status || draftNote !== (selected.follow_up_note || ''));
  const load = useCallback(async () => {
    const version = ++listVersion.current;
    setLoading(true); setError('');
    try {
      const { data } = await getFeedback({ follow_up_status: status, feedback_type: type === 'all' ? undefined : type, page, page_size: 20 });
      if (!Array.isArray(data.items) || !Number.isFinite(data.total)) throw new Error('Invalid feedback response');
      if (version === listVersion.current) {
        setRows(data.items); setTotal(data.total);
        if (!data.items.length && data.total > 0 && page > 1) setPage(page - 1);
      }
    } catch { if (version === listVersion.current) { setRows([]); setError('顾客反馈加载失败，请重试。'); } }
    finally { if (version === listVersion.current) setLoading(false); }
  }, [status, type, page]);
  useEffect(() => { void load(); return () => { listVersion.current++; }; }, [load]);
  useEffect(() => () => { detailVersion.current++; }, []);
  const fetchDetail = async (row: FeedbackRow) => {
    const version = ++detailVersion.current;
    setTarget(row); setSelected(null); setDetailLoading(true); setDetailError('');
    try {
      const { data } = await getFeedbackDetail(row.feedback_type, row.id);
      if (version !== detailVersion.current) return;
      setSelected(data); setDraftStatus(data.follow_up_status); setDraftNote(data.follow_up_note || '');
    } catch { if (version === detailVersion.current) setDetailError('反馈详情加载失败，请重试。'); }
    finally { if (version === detailVersion.current) setDetailLoading(false); }
  };
  const close = () => {
    if (savingRef.current) return;
    const discard = () => { detailVersion.current++; setTarget(null); setSelected(null); };
    if (dirty) modal.confirm({ title: '放弃未保存的处理记录？', content: '已填写的状态和说明尚未保存。', okText: '放弃修改', cancelText: '继续填写', onOk: discard });
    else discard();
  };
  const save = async () => {
    if (!selected || savingRef.current || !dirty) return;
    savingRef.current = true; setSaving(true); setDetailError('');
    const version = detailVersion.current;
    try {
      const { data } = await updateFeedbackFollowUp(selected.feedback_type, selected.id, { follow_up_status: draftStatus, follow_up_note: draftNote.trim() });
      if (version === detailVersion.current) { setSelected(data); setDraftStatus(data.follow_up_status); setDraftNote(data.follow_up_note || ''); }
      message.success('处理状态和说明已一并保存');
      await load();
    } catch { if (version === detailVersion.current) setDetailError('保存未完成，填写内容已保留。请重试保存。'); }
    finally { savingRef.current = false; setSaving(false); }
  };
  return <div className="daily-page">
    <div className="page-heading"><div><h2>顾客反馈</h2><div className="page-kicker">查看门店反馈，记录跟进进度与处理结果。</div></div><Space wrap>
      <Select aria-label="反馈类型" value={type} disabled={saving} onChange={value => { setType(value); setPage(1); }} options={typeOptions} style={{ width: 130 }} />
      <Select aria-label="跟进状态筛选" value={status} disabled={saving} onChange={value => { setStatus(value); setPage(1); }} options={Object.entries(statusText).map(([value, label]) => ({ value, label }))} style={{ width: 130 }} />
      <Button icon={<ReloadOutlined />} disabled={saving} loading={loading} onClick={() => void load()}>刷新</Button>
    </Space></div>
    <section className="daily-panel">
      {error ? <Alert type="error" showIcon message={error} action={<Button onClick={() => void load()}>重试加载</Button>} /> : <Table<FeedbackRow>
        rowKey={row => `${row.feedback_type}-${row.id}`} size="middle" loading={loading} dataSource={rows}
        locale={{ emptyText: <Empty description="暂无符合条件的反馈" /> }}
        pagination={{ current: page, pageSize: 20, total, showSizeChanger: false, onChange: setPage, showTotal: value => `共 ${value} 条` }} scroll={{ x: 1000 }}
        columns={[
          { title: '提交时间', dataIndex: 'created_at', width: 170, render: value => value ? new Date(value).toLocaleString('zh-CN') : '未提供' },
          { title: '类型', width: 110, render: (_, row) => <Tag>{feedbackTypeLabel(row.feedback_type)}</Tag> },
          { title: '来源', width: 120, render: (_, row) => feedbackSourceLabel(row) },
          { title: '评分', dataIndex: 'rating', width: 80, render: value => <Tag color={value <= 2 ? 'red' : 'gold'}>{value} 星</Tag> },
          { title: '顾客反馈', dataIndex: 'note', ellipsis: true, render: value => value || '未填写文字反馈' },
          { title: '状态', dataIndex: 'follow_up_status', width: 100, render: value => statusText[value] || '待核实' },
          { title: '操作', width: 130, fixed: 'right', render: (_, row) => <Button type="link" onClick={() => void fetchDetail(row)}>查看与处理</Button> },
        ]} />}
    </section>
    <Drawer rootClassName="daily-drawer" title="顾客反馈与跟进" width={520} open={!!target} onClose={close}
      extra={<Button type="primary" loading={saving} disabled={!selected || !dirty || detailLoading} onClick={() => void save()}>保存处理记录</Button>}>
      {detailLoading ? <Spin /> : <Space direction="vertical" size={20} style={{ width: '100%' }}>
        {detailError && <Alert type="error" showIcon message={detailError} action={!selected && target ? <Button onClick={() => void fetchDetail(target)}>重试详情</Button> : undefined} />}
        {selected && <>
          <Descriptions column={1} size="small" items={[
            { label: '类型', children: feedbackTypeLabel(selected.feedback_type) },
            { label: '来源', children: feedbackSourceLabel(selected) },
            { label: '评分', children: `${selected.rating} 星` },
            { label: '标签', children: selected.tags.join('、') || '未选择标签' },
            { label: '顾客反馈', children: selected.note || '未填写文字反馈' },
            { label: '提交时间', children: selected.created_at ? new Date(selected.created_at).toLocaleString('zh-CN') : '未提供' },
            ...(feedbackUsesServiceLink(selected) ? [{ label: '关联服务', children: selected.selection_session_id }] : []),
          ]} />
          {selected.feedback_type === 'visit_feedback' && <Typography.Text type="secondary">此反馈未关联具体服务或技师。</Typography.Text>}
          <label htmlFor="feedback-status">处理状态</label>
          <Select id="feedback-status" aria-label="处理状态" value={draftStatus} disabled={saving} onChange={setDraftStatus} options={Object.entries(statusText).map(([value, label]) => ({ value, label }))} style={{ width: '100%' }} />
          <label htmlFor="feedback-note">处理说明</label>
          <Input.TextArea id="feedback-note" value={draftNote} disabled={saving} maxLength={1000} showCount autoSize={{ minRows: 4, maxRows: 8 }} onChange={event => setDraftNote(event.target.value)} placeholder="记录已核实的情况与处理结果" />
          <Typography.Text type="secondary">{dirty ? '有未保存的修改，点击“保存处理记录”一并保存。' : selected.followed_up_at ? `最近保存：${new Date(selected.followed_up_at).toLocaleString('zh-CN')}` : '选择状态并填写说明后，一次保存。'}</Typography.Text>
        </>}
      </Space>}
    </Drawer>
  </div>;
}

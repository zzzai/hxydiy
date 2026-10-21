import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Drawer, Input, Select, Spin, Tag } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { getFeedback, getFeedbackDetail, updateFeedbackFollowUp } from '../api';

type Review = {
  id: number;
  feedback_type: 'service_review' | 'visit_feedback';
  selection_session_id: string | null;
  rating: number;
  tags: string[];
  note: string;
  follow_up_status: 'open' | 'in_progress' | 'resolved' | 'dismissed';
  follow_up_note: string;
  followed_up_at: string | null;
  created_at: string | null;
};

const statusText: Record<string, string> = { open: '待跟进', in_progress: '处理中', resolved: '已解决', dismissed: '已忽略' };
const statusColor: Record<string, string> = { open: 'red', in_progress: 'gold', resolved: 'green', dismissed: 'default' };

function timeText(value: string | null) {
  if (!value || Number.isNaN(Date.parse(value))) return '时间待核实';
  return new Date(value).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
}

/** 店长查看本店评价并记录跟进；不能修改顾客原文。 */
export default function ManagerReviewsView({ focus, onFocusConsumed, onChanged }: { focus?: { type: 'service_review'; id: number } | null; onFocusConsumed?: () => void; onChanged?: () => void }) {
  const [rows, setRows] = useState<Review[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<Review | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await getFeedback({ feedback_type: 'service_review', page: 1, page_size: 50 });
      const items = Array.isArray(response.data?.items) ? response.data.items : [];
      setRows(items.sort((left: Review, right: Review) => {
        const leftAttention = left.follow_up_status === 'open' ? 1 : 0;
        const rightAttention = right.follow_up_status === 'open' ? 1 : 0;
        return rightAttention - leftAttention
          || Number(left.rating <= 2) * -1 - Number(right.rating <= 2) * -1
          || String(right.created_at || '').localeCompare(String(left.created_at || ''));
      }));
      setError('');
    } catch {
      setError('评价加载失败，请重试');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!focus) return;
    let active = true;
    void getFeedbackDetail(focus.type, focus.id)
      .then(response => { if (active) setSelected(response.data); })
      .catch(() => undefined)
      .finally(() => { if (active) onFocusConsumed?.(); });
    return () => { active = false; };
  }, [focus?.id, focus?.type, onFocusConsumed]);

  const save = async () => {
    if (!selected || saving) return;
    setSaving(true);
    try {
      const response = await updateFeedbackFollowUp(selected.feedback_type, selected.id, {
        follow_up_status: selected.follow_up_status,
        follow_up_note: selected.follow_up_note,
      });
      setSelected(response.data);
      await load();
      onChanged?.();
    } finally {
      setSaving(false);
    }
  };

  return <section className="manager-reviews-view">
    <div className="manager-reviews-heading">
      <div><h2>顾客评价 <span>{rows.length}</span></h2><p>低分和待跟进优先；只能记录跟进，不能修改顾客原文。</p></div>
      <Button icon={<ReloadOutlined />} aria-label="刷新评价" onClick={() => void load()} loading={loading} />
    </div>
    {error && <Alert type="error" showIcon message={error} action={<Button onClick={() => void load()}>重试</Button>} />}
    {loading && !rows.length ? <div className="manager-empty"><Spin size="small" /><span>正在加载评价</span></div>
      : !rows.length ? <div className="manager-empty"><strong>暂无评价</strong><span>顾客完成服务后会在这里显示</span></div>
        : <div className="manager-review-list">{rows.map(row => <button type="button" className="manager-review-card" key={row.id} onClick={() => setSelected(row)}>
          <div className="manager-review-top"><Tag color={row.rating <= 2 ? 'red' : 'gold'}>{row.rating} 星</Tag><Tag color={statusColor[row.follow_up_status]}>{statusText[row.follow_up_status] || row.follow_up_status}</Tag></div>
          <p>{row.note || row.tags.join('、') || '顾客未填写文字'}</p>
          <div className="manager-review-meta"><span>{row.tags.join('、') || '未选择标签'}</span><time>{timeText(row.created_at)}</time></div>
        </button>)}</div>}
    <Drawer title="评价详情" placement="bottom" height="min(90dvh, 760px)" rootClassName="manager-detail-drawer" open={Boolean(selected)} onClose={() => setSelected(null)} destroyOnClose footer={<div className="manager-detail-actions"><Button size="large" onClick={() => setSelected(null)}>关闭详情</Button><Button size="large" type="primary" loading={saving} onClick={() => void save()}>保存跟进</Button></div>}>
      {selected && <>
        <div className="manager-detail-intro"><span><Tag color={selected.rating <= 2 ? 'red' : 'gold'}>{selected.rating} 星</Tag></span><Tag color={statusColor[selected.follow_up_status]}>{statusText[selected.follow_up_status]}</Tag></div>
        <p className="manager-review-note">{selected.note || '顾客未填写文字评价'}</p>
        <dl className="manager-detail-meta">
          <div><dt>标签</dt><dd>{selected.tags.join('、') || '未选择标签'}</dd></div>
          <div><dt>时间</dt><dd>{timeText(selected.created_at)}</dd></div>
          <div><dt>订单</dt><dd>{selected.selection_session_id ? selected.selection_session_id.slice(-8) : '未关联服务单'}</dd></div>
        </dl>
        <label className="manager-action-form">跟进状态<Select value={selected.follow_up_status} onChange={value => setSelected({ ...selected, follow_up_status: value as Review['follow_up_status'] })} options={Object.entries(statusText).map(([value, label]) => ({ value, label }))} /></label>
        <label className="manager-action-form">跟进备注<Input.TextArea maxLength={1000} autoSize={{ minRows: 3, maxRows: 8 }} value={selected.follow_up_note} onChange={event => setSelected({ ...selected, follow_up_note: event.target.value })} placeholder="记录跟进结果，不要填写无关顾客隐私" /></label>
      </>}
    </Drawer>
  </section>;
}

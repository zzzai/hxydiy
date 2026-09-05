import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Empty, Pagination, Segmented, Spin, Tag, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { getTechnicianServiceHistory } from '../api';
import { technicianProfileStatusLabel } from './technicianMobile';

type ProfileStatus = 'all' | 'confirmed' | 'pending';
type HistoryItem = {
  occupancy_id: number;
  completed_at: string;
  duration_minutes: number | null;
  profile_status: 'confirmed' | 'pending';
  customer: { display_name: string };
  projects: string[];
  service_position: string;
  profile_summary: Record<string, unknown> | null;
};

const summaryText = (summary: Record<string, unknown> | null) => {
  if (!summary) return '本次尚未形成顾客确认的长期摘要';
  return Object.entries(summary)
    .filter(([key]) => !['schema_version', 'taxonomy_version'].includes(key))
    .flatMap(([, value]) => Array.isArray(value) ? value : value == null ? [] : [String(value)])
    .join(' · ') || '已有顾客确认记录';
};

export default function TechnicianServiceHistoryPage() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<ProfileStatus>('all');
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    try {
      const response = await getTechnicianServiceHistory(page, 20, status);
      setItems(response.data?.items || []);
      setTotal(response.data?.total || 0);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, [page, status]);

  useEffect(() => { void load(); }, [load]);

  return <section className="technician-own-history">
    <div className="technician-history-toolbar">
      <Segmented block value={status} options={[{ label: '全部', value: 'all' }, { label: '待补记', value: 'pending' }, { label: '已确认', value: 'confirmed' }]} onChange={(value) => { setPage(1); setStatus(value as ProfileStatus); }} />
      <Button aria-label="刷新本人历史" icon={<ReloadOutlined />} onClick={() => void load()} loading={loading} />
    </div>
    {failed ? <Alert type="error" showIcon message="本人历史加载失败" description="请检查网络后重试。" action={<Button size="small" onClick={() => void load()}>重试</Button>} />
      : loading && !items.length ? <div className="technician-loading"><Spin /></div>
        : !items.length ? <div className="technician-empty-state">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={status === 'all' ? '尚无本人已完成服务' : status === 'confirmed' ? '尚无顾客已确认记录' : '尚无待补记服务'} />
          {status === 'all' && <Typography.Paragraph type="secondary">旧数据未关联到明确服务技师时，不会猜测归入本人历史。</Typography.Paragraph>}
        </div> : <>
          <div className="technician-history-list">{items.map((item) => <article className="technician-history-card" key={item.occupancy_id}>
            <div className="technician-history-card-main">
              <div className="technician-history-card-headline"><strong>{item.service_position || '服务位'}</strong><Tag color={item.profile_status === 'confirmed' ? 'green' : 'gold'}>{technicianProfileStatusLabel(item.profile_status)}</Tag></div>
              <span>{new Date(item.completed_at).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })} · {item.duration_minutes == null ? '时长未记录' : `${item.duration_minutes} 分钟`}</span>
              <span>{item.customer?.display_name || '匿名顾客'} · {item.projects?.join('、') || '项目未记录'}</span>
              <Typography.Paragraph className="technician-history-summary">{summaryText(item.profile_summary)}</Typography.Paragraph>
            </div>
          </article>)}</div>
          {total > 20 && <Pagination current={page} pageSize={20} total={total} showSizeChanger={false} onChange={setPage} />}
        </>}
  </section>;
}

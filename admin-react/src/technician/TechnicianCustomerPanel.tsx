import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Drawer, Empty, Pagination, Select, Spin, Tabs, Tag } from 'antd';
import {
  addTechnicianCustomerTag, getTechnicianCustomerHistory, getTechnicianCustomerReport,
  getTechnicianCustomerReports, getTechnicianCustomerReviews, getTechnicianCustomerSummary,
  getTechnicianCustomerTags, revokeTechnicianCustomerTag,
} from '../api';
import type { CustomerHistoryItem, CustomerReportDetail, CustomerReportItem, CustomerReviewItem, CustomerSummary, CustomerTags } from '../technicianCustomer';
import { useTechnicianSession } from './useTechnicianSession';

type Section = 'history' | 'reviews' | 'reports' | 'tags';
const sections = [{ key: 'history', label: '服务历史' }, { key: 'reviews', label: '顾客反馈' }, { key: 'reports', label: '检测报告' }, { key: 'tags', label: '运营标签' }];
const dateLabel = (value: string | null) => value && !Number.isNaN(Date.parse(value)) ? new Date(value).toLocaleDateString('zh-CN') : '日期未记录';
const projectLabel = (items: { name: string; quantity: number }[]) => items.map((item) => `${item.name} × ${item.quantity}`).join('、');

export default function TechnicianCustomerPanel({ occupancyId, onClose }: { occupancyId: number; onClose: () => void }) {
  const current = useTechnicianSession();
  const [summary, setSummary] = useState<CustomerSummary>();
  const [section, setSection] = useState<Section>('tags');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [history, setHistory] = useState<CustomerHistoryItem[]>([]);
  const [reviews, setReviews] = useState<CustomerReviewItem[]>([]);
  const [reports, setReports] = useState<CustomerReportItem[]>([]);
  const [detail, setDetail] = useState<CustomerReportDetail>();
  const [tags, setTags] = useState<CustomerTags>();
  const [tagId, setTagId] = useState<number>();
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [reload, setReload] = useState(0);
  const [summaryRetry, setSummaryRetry] = useState(0);
  const mutation = useRef(false);
  const tagIntent = useRef<{ tagId: number; key: string }>();
  const request = useRef(0);

  const failure = (reason: any, reportsOnly = false) => {
    if (!current()) return;
    const status = reason?.response?.status;
    if (status === 404 || status === 409 || (status === 403 && !reportsOnly)) { onClose(); return; }
    setError(reportsOnly && status === 403 ? '报告暂不可用，未取得本次服务所需的查看权限。' : '资料加载失败，请重试。');
  };
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    void getTechnicianCustomerSummary(occupancyId).then(({ data }) => {
      if (active && current()) { setSummary(data); setLoading(false); }
    }).catch((reason) => { if (active) { failure(reason); setLoading(false); } });
    return () => { active = false; };
  }, [occupancyId, current, summaryRetry]);

  useEffect(() => {
    if (summary?.access !== 'granted') return;
    const id = ++request.current;
    let active = true;
    const valid = () => active && current() && id === request.current;
    setLoading(true); setError(''); setDetail(undefined); setHistory([]); setReviews([]); setReports([]); setTags(undefined); setTotal(0);
    const load = async () => {
      try {
        if (section === 'history') {
          const { data } = await getTechnicianCustomerHistory(occupancyId, page);
          if (valid()) { setHistory(data.items); setTotal(data.total); }
        } else if (section === 'reviews') {
          const { data } = await getTechnicianCustomerReviews(occupancyId, page);
          if (valid()) { setReviews(data.items); setTotal(data.total); }
        } else if (section === 'reports') {
          const { data } = await getTechnicianCustomerReports(occupancyId, page);
          if (valid()) { setReports(data.items); setTotal(data.total); }
        } else {
          const { data } = await getTechnicianCustomerTags(occupancyId);
          if (valid()) setTags(data);
        }
      } catch (reason) { if (valid()) failure(reason, section === 'reports'); }
      finally { if (valid()) setLoading(false); }
    };
    void load();
    return () => { active = false; };
  }, [summary, section, page, reload, occupancyId, current]);

  const openReport = async (reportId: string) => {
    const id = ++request.current;
    setDetail(undefined); setLoading(true); setError('');
    try {
      const { data } = await getTechnicianCustomerReport(occupancyId, reportId);
      if (current() && id === request.current) setDetail(data);
    } catch (reason) { if (current() && id === request.current) failure(reason, true); }
    finally { if (current() && id === request.current) setLoading(false); }
  };
  const mutateTag = async (action: () => Promise<unknown>, message: string) => {
    if (mutation.current) return;
    mutation.current = true; setBusy(true); setNotice(''); setError('');
    try {
      await action();
      if (!current()) return;
      const { data } = await getTechnicianCustomerTags(occupancyId);
      if (!current()) return;
      setTags(data); setNotice(message);
    } catch (reason: any) {
      if (reason?.response?.status === 409 && current()) { setError('标签已变化，请重新加载后查看。'); }
      else failure(reason);
    } finally { mutation.current = false; if (current()) setBusy(false); }
  };
  const addTag = () => {
    if (!tagId) return;
    if (tagIntent.current?.tagId !== tagId) tagIntent.current = { tagId, key: crypto.randomUUID() };
    const intent = tagIntent.current;
    void mutateTag(async () => {
      await addTechnicianCustomerTag(occupancyId, intent.tagId, intent.key);
      if (current()) { tagIntent.current = undefined; setTagId(undefined); }
    }, '标签已添加');
  };

  return <Drawer title="顾客资料" placement="bottom" height="90dvh" open onClose={onClose} destroyOnClose>
    <div className="technician-customer-panel">
      {summary && <header><h2>{summary.customer_name || '本次顾客'}</h2><p>{summary.membership?.level || '未提供会员等级'}</p></header>}
      {summary?.access === 'unbound' ? <Alert type="info" message="本次服务尚未关联顾客资料，可正常继续服务。" /> : <>
        {summary && <Tabs activeKey={section} items={sections.map((item) => ({ ...item, disabled: busy }))} onChange={(value) => { ++request.current; setSection(value as Section); setPage(1); setNotice(''); }} />}
        {error && <Alert type="warning" message={error} action={<Button onClick={() => { if (!summary) setSummaryRetry((value) => value + 1); else setReload((value) => value + 1); }}>重新加载</Button>} />}
        {notice && <p role="status">{notice}</p>}
        {loading ? <Spin /> : !error && summary?.access === 'granted' && <>
          {section === 'history' && (history.length ? history.map((item) => <article key={item.id} className="technician-customer-entry"><time>{dateLabel(item.service_finished_at || item.service_started_at)}</time><p>{projectLabel(item.projects) || '未记录项目'}</p></article>) : <Empty description="暂无服务历史" />)}
          {section === 'reviews' && (reviews.length ? reviews.map((item) => <article key={`${item.feedback_type}:${item.id}`} className="technician-customer-entry"><h3>{item.feedback_type === 'visit' ? '到店反馈' : '服务评价'}</h3><time>{dateLabel(item.created_at)}</time>{item.rating !== null && <p>评分：{item.rating}</p>}{item.feedback_type === 'service' && item.projects.length > 0 && <p>{projectLabel(item.projects)}</p>}<p>{item.content || '顾客未填写文字'}</p>{item.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}</article>) : <Empty description="暂无顾客反馈" />)}
          {section === 'reports' && (detail ? <article className="technician-customer-entry"><Button onClick={() => setDetail(undefined)}>返回报告列表</Button><h3>{detail.title}</h3>{detail.sections.map((item, index) => <section key={index}><h4>{item.title}</h4><p style={{ whiteSpace: 'pre-wrap' }}>{item.content}</p></section>)}</article> : reports.length ? reports.map((item) => <article key={item.id} className="technician-customer-entry"><time>{dateLabel(item.created_at)}</time><Button block onClick={() => void openReport(item.id)}>{item.title}</Button></article>) : <Empty description="暂无可查看的报告" />)}
          {section === 'tags' && tags && <>
            <p>仅记录普通运营标签，与本次服务记录分开保存。</p>
            {tags.items.map((tag) => <article key={tag.id} className="technician-customer-entry"><strong>{tag.name}</strong>
              {tag.sources.some((source) => source.kind === 'legacy') && <p>含门店已有记录</p>}
              {tag.sources.filter((source) => source.kind === 'contribution' && source.owned_by_me && source.contribution_id !== null && source.version !== null).map((source) => <Button key={source.contribution_id} disabled={busy} onClick={() => void mutateTag(() => revokeTechnicianCustomerTag(occupancyId, source.contribution_id!, source.version!, '撤回本人添加的标签'), '已撤回本人添加，其他来源不受影响')}>撤回本人添加</Button>)}
            </article>)}
            {!tags.items.length && <Empty description="暂无运营标签" />}
            <Select aria-label="选择运营标签" style={{ width: '100%' }} value={tagId} disabled={busy} placeholder="选择已有标签" onChange={setTagId} options={tags.available_tags.map((tag) => ({ value: tag.id, label: tag.name, disabled: tags.items.some((item) => item.id === tag.id && item.sources.some((source) => source.owned_by_me)) }))} />
            <Button type="primary" block disabled={!tagId || busy} loading={busy} onClick={addTag}>添加标签</Button>
          </>}
          {section !== 'tags' && !detail && total > 20 && <Pagination simple current={page} total={total} pageSize={20} onChange={setPage} />}
        </>}
      </>}
    </div>
  </Drawer>;
}

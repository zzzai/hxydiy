import { useEffect, useRef, useState } from 'react';
import { ApiError, getTcmReport, getTcmReportConsent, getTcmReports, updateTcmReportConsent, type TcmReportConsent, type TcmReportDetail, type TcmReportList } from '../api';
import { formatDateTime } from '../profile';
import { reportsByDate } from '../tcmReports';

export default function MyReports({ token, onBack, onVerify }: { token: string; onBack: () => void; onVerify: () => void }) {
  const [consent, setConsent] = useState<TcmReportConsent | null>(null);
  const [accepted, setAccepted] = useState(false);
  const [list, setList] = useState<TcmReportList | null>(null);
  const [detail, setDetail] = useState<TcmReportDetail | null>(null);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);

  async function run(action: (signal: AbortSignal) => Promise<void>) {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    setBusy(true);
    setError(null);
    try { await action(current.signal); }
    catch (reason) { if (!current.signal.aborted) setError(reason instanceof Error ? reason : new Error('暂时无法查看报告，请稍后重试')); }
    finally { if (!current.signal.aborted) setBusy(false); }
  }

  async function load(signal: AbortSignal) {
    const status = await getTcmReportConsent(token, signal);
    if (signal.aborted) return;
    setConsent(status);
    if (status.consented) {
      const reports = await getTcmReports(token, 0, signal);
      if (!signal.aborted) setList(reports);
    }
  }

  useEffect(() => {
    void run(load);
    return () => { controller.current?.abort(); };
  }, [token]);

  const verificationRequired = error instanceof ApiError && (error.status === 401 || error.code === 'PHONE_VERIFICATION_REQUIRED');
  const message = error instanceof ApiError && ['TCM_UNAVAILABLE', 'TCM_SOURCE_INVALID'].includes(error.code)
    ? '检测报告服务暂时不可用，请稍后再试。' : error?.message;

  return <section className="my-reports" aria-label="我的检测报告">
    <div className="my-reports-heading"><h2>我的检测报告</h2><button type="button" onClick={onBack}>返回个人中心</button></div>
    <p className="my-reports-note">仅查看本人检测结果。结果来自检测服务，不构成医学诊断。</p>
    {busy && <p role="status">正在加载…</p>}
    {error && <div role="alert"><p>{message}</p>{verificationRequired ? <button type="button" onClick={onVerify}>验证手机号</button> : <button type="button" disabled={busy} onClick={() => { setDetail(null); setList(null); void run(load); }}>重新加载</button>}</div>}
    {consent && !consent.consented && <div className="my-reports-consent">
      <h3>查看前，请确认授权</h3><p>{consent.notice}</p>
      <label><input type="checkbox" checked={accepted} onChange={event => setAccepted(event.target.checked)} />我已阅读并单独同意查看本人健康检测报告</label>
      <button className="primary" type="button" disabled={!accepted || busy} onClick={() => void run(async signal => {
        const status = await updateTcmReportConsent(token, consent.version, signal);
        if (signal.aborted) return;
        setConsent(status);
        if (status.consented) { const reports = await getTcmReports(token, 0, signal); if (!signal.aborted) setList(reports); }
      })}>同意并查看</button>
    </div>}
    {consent?.consented && !error && !detail && list && <div className="my-reports-list">
      {!list.items.length && <p>当前手机号暂无检测报告。如检测时使用其他号码，可重新验证该号码。</p>}
      {reportsByDate(list.items).map(report => <button type="button" key={report.report_id} disabled={busy} onClick={() => void run(async signal => { const result = await getTcmReport(token, report.report_id, signal); if (!signal.aborted) setDetail(result); })}><strong>{report.title}</strong><span>{report.reported_at ? formatDateTime(report.reported_at) : '检测时间未提供'}</span><span>查看结果</span></button>)}
      {list.has_more && <button type="button" disabled={busy} onClick={() => void run(async signal => { const next = await getTcmReports(token, list.offset + list.limit, signal); if (!signal.aborted) setList({ ...next, items: [...new Map([...list.items, ...next.items].map(item => [item.report_id, item])).values()] }); })}>加载更多</button>}
    </div>}
    {consent?.consented && !error && detail && <article className="my-reports-detail">
      <button type="button" onClick={() => setDetail(null)}>返回报告列表</button><h3>{detail.title}</h3><p>{detail.reported_at ? formatDateTime(detail.reported_at) : '检测时间未提供'}</p>
      <h4>体质得分（原始结果）</h4><dl>{detail.physiques.length ? detail.physiques.map((item, index) => <div key={index}><dt>{item.name}</dt><dd>{item.score ?? '未提供'}</dd></div>) : <p>未提供体质得分</p>}</dl>
      <h4>检测数值（原始结果）</h4><dl>{[['心率', detail.heart_rate], ['血氧', detail.blood_oxygen], ['湿气', detail.moisture]].map(([name, value]) => <div key={String(name)}><dt>{name}</dt><dd>{value ?? '未提供'}</dd></div>)}</dl>
    </article>}
    <div className="my-reports-actions">
      <button type="button" disabled={busy} onClick={onVerify}>重新验证其他号码</button>
      {(consent?.consented || verificationRequired) && <button type="button" disabled={busy} onClick={() => {
        setDetail(null); setList(null); setAccepted(false);
        void run(async signal => { const status = await updateTcmReportConsent(token, null, signal); if (!signal.aborted) setConsent(status); });
      }}>撤回报告查看授权</button>}
    </div>
  </section>;
}

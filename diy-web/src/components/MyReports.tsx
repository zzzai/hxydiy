import { useEffect, useRef, useState } from 'react';
import { ChevronRight, FileHeart, ShieldCheck, CircleAlert } from 'lucide-react';
import { ApiError, getTcmReport, getTcmReportConsent, getTcmReports, updateTcmReportConsent, type TcmReportConsent, type TcmReportList } from '../api';
import { formatDateTime } from '../profile';
import { reportsByDate, verifiedOriginalReportUrl } from '../tcmReports';

export default function MyReports({ token, onVerify }: { token: string; onVerify: () => void }) {
  const [consent, setConsent] = useState<TcmReportConsent | null>(null);
  const [accepted, setAccepted] = useState(false);
  const [list, setList] = useState<TcmReportList | null>(null);
  const [openingReport, setOpeningReport] = useState(false);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const running = useRef(false);

  async function run(action: (signal: AbortSignal) => Promise<void>) {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    running.current = true;
    setBusy(true);
    setError(null);
    try { await action(current.signal); }
    catch (reason) { if (!current.signal.aborted) {
      if (reason instanceof ApiError && [401, 403].includes(reason.status)) {
        setConsent(value => value ? { ...value, consented: false } : value);
        setList(null); setAccepted(false);
      }
      setError(reason instanceof TypeError ? new Error('网络连接失败，请检查网络后重试。') : reason instanceof Error ? reason : new Error('暂时无法查看报告，请稍后重试'));
    } }
    finally { if (!current.signal.aborted) { running.current = false; setBusy(false); } }
  }

  async function load(signal: AbortSignal) {
    setOpeningReport(false);
    const status = await getTcmReportConsent(token, signal);
    if (signal.aborted) return;
    setConsent(status);
    if (!status.consented) { setList(null); setAccepted(false); return; }
    if (status.consented) {
      const reports = await getTcmReports(token, 0, signal);
      if (!signal.aborted) setList(reports);
    }
  }

  useEffect(() => {
    void run(load);
    return () => { controller.current?.abort(); };
  }, [token]);

  useEffect(() => {
    if (!consent?.consented) return;
    let scheduled: ReturnType<typeof setTimeout> | undefined;
    let lastRefresh = 0;
    const refreshWhenVisible = () => {
      if (document.visibilityState !== 'visible' || running.current) return;
      clearTimeout(scheduled);
      scheduled = setTimeout(() => {
        if (document.visibilityState === 'visible' && !running.current && Date.now() - lastRefresh >= 1000) {
          lastRefresh = Date.now();
          void run(load);
        }
      }, 200);
    };
    window.addEventListener('focus', refreshWhenVisible);
    document.addEventListener('visibilitychange', refreshWhenVisible);
    return () => {
      clearTimeout(scheduled);
      window.removeEventListener('focus', refreshWhenVisible);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
    };
  }, [token, consent?.consented]);

  const phoneVerificationRequired = error instanceof ApiError && error.code === 'PHONE_VERIFICATION_REQUIRED';
  const loginRequired = error instanceof ApiError && error.status === 401 && !phoneVerificationRequired;
  const verificationRequired = phoneVerificationRequired || loginRequired;
  const consentRequired = error instanceof ApiError && error.status === 403 && error.code === 'TCM_CONSENT_REQUIRED';
  const message = error instanceof ApiError && ['TCM_UNAVAILABLE', 'TCM_SOURCE_INVALID'].includes(error.code)
    ? '检测报告服务暂时不可用，请稍后再试。' : error?.message;

  return <section className="my-reports" aria-label="我的检测报告">
    <p className="my-reports-note"><ShieldCheck size={16} aria-hidden="true" />仅查看本人检测结果，不构成医学诊断。</p>
    {consent?.consented && <button className="my-reports-link" type="button" disabled={busy} onClick={() => void run(load)}>刷新报告</button>}
    {busy && <p className="my-reports-loading" role="status">正在加载…</p>}
    {error && <div className="my-reports-error" role="alert"><CircleAlert size={24} aria-hidden="true" /><h3>{phoneVerificationRequired ? '请验证检测手机号' : loginRequired ? '登录已过期，请重新登录' : consentRequired ? '请重新确认报告授权' : openingReport ? '暂时无法打开完整报告' : list ? '报告刷新未完成' : '暂时无法查看报告'}</h3><p>{message}</p>{verificationRequired ? <button type="button" onClick={onVerify}>{loginRequired ? '重新登录' : '验证手机号'}</button> : <button type="button" disabled={busy} onClick={() => void run(load)}>重新加载</button>}</div>}
    {consent && !consent.consented && !verificationRequired && (!error || consentRequired) && <div className="my-reports-consent">
      <div className="my-reports-consent-title"><ShieldCheck size={22} aria-hidden="true" /><h3>查看前，请确认授权</h3></div><p>{consent.notice}</p>
      <label><input type="checkbox" checked={accepted} onChange={event => setAccepted(event.target.checked)} />我已阅读并单独同意查看本人健康检测报告</label>
      <button className="primary" type="button" disabled={!accepted || busy} onClick={() => void run(async signal => {
        const status = await updateTcmReportConsent(token, consent.version, signal);
        if (signal.aborted) return;
        setConsent(status);
        if (status.consented) { const reports = await getTcmReports(token, 0, signal); if (!signal.aborted) setList(reports); }
      })}>同意并查看</button>
    </div>}
    {consent?.consented && !verificationRequired && list && <div className="my-reports-list">
      {!list.items.length && <div className="my-reports-empty"><span className="my-reports-empty-icon"><FileHeart size={32} strokeWidth={1.5} aria-hidden="true" /></span><h3>还没有检测报告</h3><p>还没做过检测？到店后可联系前台，安排体质检测。</p><p className="my-reports-empty-hint">已做过检测？请确认登录的是检测时使用的手机号。</p></div>}
      {reportsByDate(list.items).map(report => <button className="my-reports-row" type="button" key={report.report_id} disabled={busy} onClick={() => {
        setOpeningReport(true);
        void run(async signal => {
          const result = await getTcmReport(token, report.report_id, signal);
          if (signal.aborted) return;
          const url = result.report_id === report.report_id ? verifiedOriginalReportUrl(result.original_report_url, report.report_id) : null;
          if (!url) throw new Error('完整报告地址暂不可用，请稍后重试或联系门店。');
          const link = document.createElement('a');
          link.href = url; link.target = '_self'; link.rel = 'noopener noreferrer'; link.referrerPolicy = 'no-referrer';
          link.click();
        });
      }}><FileHeart size={22} strokeWidth={1.5} aria-hidden="true" /><span><strong>{report.title}</strong><time>{report.reported_at ? formatDateTime(report.reported_at) : '检测时间未提供'}</time></span><ChevronRight size={18} aria-hidden="true" /></button>)}
      {list.has_more && <button type="button" disabled={busy} onClick={() => void run(async signal => { const next = await getTcmReports(token, list.offset + list.limit, signal); if (!signal.aborted) setList({ ...next, items: [...new Map([...list.items, ...next.items].map(item => [item.report_id, item])).values()] }); })}>加载更多</button>}
    </div>}
    <div className="my-reports-actions"><p>检测时使用了其他手机号？</p>
      <button className="my-reports-link" type="button" onClick={onVerify}>重新验证其他号码</button>
    </div>
      {(consent?.consented || verificationRequired || consentRequired) && <div className="my-reports-permission"><div><strong>报告查看授权</strong><p>可随时撤回，撤回后将停止查看。</p></div><button className="my-reports-link" type="button" onClick={() => {
        setConsent(value => value ? { ...value, consented: false } : value);
        setList(null); setAccepted(false); setOpeningReport(false);
        void run(async signal => { const status = await updateTcmReportConsent(token, null, signal); if (!signal.aborted) setConsent(status); });
      }}>撤回授权</button></div>}
  </section>;
}

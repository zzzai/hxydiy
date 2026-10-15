import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ChevronDown, ChevronRight } from 'lucide-react';
import { ApiError, getCurrentCustomer, type TcmReportSummary } from '../api';
import { clearCustomerAuth, CUSTOMER_SESSION_REFRESH_INTERVAL_MS, isCustomerAuthTokenActive, readCustomerAuth, writeCustomerAuth, type CustomerAuth } from '../customerAuth';
import { maskedPhone, formatDateTime } from '../profile';
import { openOriginalReport, originalReportUrl, resolveReportEntry, loadReportIndex, shouldAutoOpenReport } from '../tcmReports';
import { serviceAccountEntry, reportEntryUrl, reportEntryHasBack } from '../returnEntry';
import RecordLoginDialog from './RecordLoginDialog';

export default function ReportEntryPage() {
  const [auth, setAuth] = useState<CustomerAuth | null>(readCustomerAuth);
  const [loginOpen, setLoginOpen] = useState(() => !readCustomerAuth());
  const [history, setHistory] = useState(false);
  const [center, setCenter] = useState(false);
  const [reports, setReports] = useState<TcmReportSummary[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(() => Boolean(readCustomerAuth()));
  const [message, setMessage] = useState('');
  const controller = useRef<AbortController | null>(null);
  const running = useRef(false);
  const navigationType = (window.performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined)?.type;
  const returnedFromReport = useRef(!shouldAutoOpenReport(window.history.state, navigationType));
  const storeId = Number(new URLSearchParams(window.location.search).get('store') || 1);
  const menuUrl = serviceAccountEntry(window.location.origin, storeId, 'projects');
  const hasPreviousPage = useRef(reportEntryHasBack(window.history.state, window.history.length, document.referrer));
  useEffect(() => { window.history.replaceState({ ...window.history.state, hxy_report_entry_back: hasPreviousPage.current }, '', reportEntryUrl(window.location.origin, storeId)); }, [storeId]);

  function clearView() {
    controller.current?.abort();
    running.current = false;
    setBusy(false); setChecking(false); setHistory(false); setMessage('');
    setCenter(false); setReports(null);
  }

  function verifyNumber(note = '') {
    returnedFromReport.current = false;
    clearView(); clearCustomerAuth(); setAuth(null); setLoginOpen(true); setMessage(note);
  }

  function finishEntry(result: Awaited<ReturnType<typeof resolveReportEntry>>) {
    if (result.kind === 'ready') {
      navigateOriginal(result.url);
    } else {
      setCenter(true);
      if (result.kind === 'empty') setReports([]);
      setMessage(result.kind === 'empty' ? '还没有检测报告。已做过检测？请确认登录的是检测时登记的手机号。' : '检测时间未提供或无法确定最近一次，请在历史报告中选择。');
    }
  }

  function navigateOriginal(url: string) {
    returnedFromReport.current = true; setCenter(true);
    window.history.replaceState({ ...window.history.state, hxy_report_original_opened: true, hxy_report_history_open: history }, '');
    openOriginalReport(url);
  }

  async function loadCenter(token: string, signal: AbortSignal) {
    const items = await loadReportIndex(token, signal);
    if (signal.aborted) return;
    setReports(items); setCenter(true); setHistory(Boolean(window.history.state?.hxy_report_history_open));
    setMessage(items.length ? '' : '这个手机号下暂时没有检测报告。');
  }

  function back() {
    clearView();
    if (hasPreviousPage.current) window.history.back();
    else window.location.replace(menuUrl);
  }

  function showError(reason: unknown) {
    if (reason instanceof ApiError && (reason.status === 401 || reason.code === 'PHONE_VERIFICATION_REQUIRED')) {
      verifyNumber(reason.status === 401 ? '登录已过期，请重新登录。' : '请验证检测时登记的手机号。');
      return;
    }
    if (reason instanceof ApiError && reason.status === 403) {
      setHistory(false); setReports(null); setCenter(false);
    }
    setMessage(reason instanceof TypeError ? '网络连接失败，请稍后重试。' : reason instanceof ApiError && ['TCM_UNAVAILABLE', 'TCM_SOURCE_INVALID'].includes(reason.code) ? '检测报告服务暂时不可用，请稍后再试。' : reason instanceof Error ? reason.message : '暂时无法查看报告，请稍后再试。');
  }

  useEffect(() => {
    if (!auth) { setChecking(false); return; }
    clearView();
    const token = auth.token;
    const identityController = new AbortController();
    const entryController = new AbortController();
    controller.current = entryController;
    let active = true;
    let refreshing: Promise<boolean> | null = null;
    setChecking(true);
    async function refreshIdentity() {
      if (!active || identityController.signal.aborted) return false;
      if (refreshing) return refreshing;
      const request = (async () => {
        try {
          if (!isCustomerAuthTokenActive(token)) throw new ApiError(401, '登录已过期');
          const user = await getCurrentCustomer(token);
          if (!active || identityController.signal.aborted) return false;
          if (user.id !== auth!.user.id || user.phone !== auth!.user.phone) throw new ApiError(401, '登录号码已更新');
          writeCustomerAuth({ token, user });
          return true;
        } catch (reason) { if (active && !identityController.signal.aborted) showError(reason); return false; }
      })();
      refreshing = request;
      try { return await request; }
      finally { if (refreshing === request) refreshing = null; }
    }
    async function enter() {
      try {
        if (!await refreshIdentity() || !active || entryController.signal.aborted) return;
        if (returnedFromReport.current) {
          await loadCenter(token, entryController.signal);
          return;
        }
        const result = await resolveReportEntry(token, entryController.signal);
        if (active && !entryController.signal.aborted) finishEntry(result);
      } catch (reason) { if (active && !entryController.signal.aborted) showError(reason); }
      finally { if (active && !entryController.signal.aborted) setChecking(false); }
    }
    void enter();
    const whenVisible = () => { if (document.visibilityState === 'visible') void refreshIdentity(); };
    const timer = window.setInterval(whenVisible, CUSTOMER_SESSION_REFRESH_INTERVAL_MS);
    window.addEventListener('focus', whenVisible);
    const whenRestored = (event: PageTransitionEvent) => {
      if (!event.persisted) return;
      returnedFromReport.current = true;
      running.current = false; setBusy(false);
      entryController.abort();
      controller.current?.abort();
      const restored = new AbortController(); controller.current = restored;
      setChecking(true);
      void (async () => {
        try {
          if (!await refreshIdentity() || !active || restored.signal.aborted) return;
          await loadCenter(token, restored.signal);
        } catch (reason) { if (active && !restored.signal.aborted) showError(reason); }
        finally { if (active && !restored.signal.aborted) setChecking(false); }
      })();
    };
    window.addEventListener('pageshow', whenRestored);
    document.addEventListener('visibilitychange', whenVisible);
    return () => {
      active = false; identityController.abort(); entryController.abort(); controller.current?.abort();
      window.clearInterval(timer);
      window.removeEventListener('focus', whenVisible);
      window.removeEventListener('pageshow', whenRestored);
      document.removeEventListener('visibilitychange', whenVisible);
    };
  }, [auth?.token]);

  async function viewReport(kind: 'latest' | 'history', reportId?: string) {
    if (!auth || running.current || checking) return;
    const current = new AbortController();
    controller.current?.abort(); controller.current = current; running.current = true;
    setBusy(true); setMessage('');
    try {
      if (kind === 'history') {
        await loadCenter(auth.token, current.signal);
        if (!current.signal.aborted) setHistory(true);
        return;
      }
      if (reportId) {
        const url = await originalReportUrl(auth.token, reportId, current.signal);
        if (!current.signal.aborted) navigateOriginal(url);
        return;
      }
      const result = await resolveReportEntry(auth.token, current.signal);
      if (current.signal.aborted) return;
      finishEntry(result);
    } catch (reason) { if (!current.signal.aborted) showError(reason); }
    finally { if (!current.signal.aborted) { running.current = false; setBusy(false); } }
  }

  const latest = reports?.length && reports.every(item => item.reported_at && Number.isFinite(Date.parse(item.reported_at)))
    && (reports.length === 1 || Date.parse(reports[0].reported_at!) !== Date.parse(reports[1].reported_at!)) ? reports[0] : null;
  const olderReports = latest ? reports!.slice(1) : reports || [];

  return <div className="report-entry-page">
    <header><button type="button" aria-label="返回" onClick={back}><ArrowLeft size={22} /></button><strong>荷小悦</strong><details className="report-entry-more"><summary>更多</summary><div>
      {auth && <><p>{maskedPhone(auth.user.phone)}</p><button type="button" onClick={() => verifyNumber()}>换个号码</button></>}
    </div></details></header>
    <main>
        <section className="report-entry-intro">
          <div className="report-entry-brand-copy"><h1 aria-label="我的检测报告">我的<br />检测报告</h1><p className="report-entry-brand-caption">查看最近一次及历史报告</p></div>
          <img className="report-entry-brand-ip" src="/assets/seat-entry-ip.png" width={144} height={144} alt="" loading="eager" decoding="async" />
        </section>
        {(checking || busy) && <p role="status">{center || returnedFromReport.current ? '正在加载本人报告…' : '正在打开本人报告…'}</p>}
        {message && <p className="report-entry-message" role="alert">{message}</p>}
        {center && auth && !checking && !busy ? <section className="report-entry-results" aria-label="检测报告">
          {latest && <div className="report-entry-latest"><span className="report-entry-latest-label">最近一次检测</span><time dateTime={latest.reported_at!}>{formatDateTime(latest.reported_at)}</time><button className="report-entry-primary" type="button" onClick={() => void viewReport('latest', latest.report_id)}>查看报告<ChevronRight size={18} aria-hidden="true" /></button></div>}
          {olderReports.length > 0 && <details className="report-entry-disclosure" open={history} onToggle={event => {
            const expanded = event.currentTarget.open; setHistory(expanded);
            window.history.replaceState({ ...window.history.state, hxy_report_history_open: expanded }, '');
          }}><summary>历史报告<ChevronDown size={20} aria-hidden="true" /></summary><ul>{olderReports.map(item => <li key={item.report_id}><div><strong>检测报告</strong><time dateTime={item.reported_at || undefined}>{item.reported_at ? formatDateTime(item.reported_at) : '检测时间未提供'}</time></div><button type="button" onClick={() => void viewReport('latest', item.report_id)}>查看报告</button></li>)}</ul></details>}
          {reports === null && <button className="report-entry-history" type="button" onClick={() => void viewReport('history')}>查看历史报告</button>}
          {reports?.length === 0 && <button className="report-entry-history" type="button" onClick={() => verifyNumber()}>换个手机号</button>}
        </section> : !auth ? <button className="report-entry-primary" type="button" onClick={() => setLoginOpen(true)}>登录并查看报告<ChevronRight size={18} aria-hidden="true" /></button> : <>
          {!checking && !busy && <><button className="report-entry-primary" type="button" onClick={() => void viewReport('latest')}>再次查看报告<ChevronRight size={18} aria-hidden="true" /></button><button className="report-entry-history" type="button" onClick={() => void viewReport('history')}>历史报告</button></>}
        </>}
      <a className="report-entry-menu" href={menuUrl} aria-label="DIY 定制我的项目">
        <span className="report-entry-menu-copy"><strong>DIY 定制我的项目</strong><span>按喜好搭配，选适合自己的项目</span></span>
        <ChevronRight size={20} aria-hidden="true" />
      </a>
    </main>
    <RecordLoginDialog key={loginOpen ? 'login' : 'closed'} open={loginOpen} selectionSessionId="" selectionToken="" purpose="report" notice={message} onClose={back} onSuccess={next => { returnedFromReport.current = false; clearView(); setAuth(next); setLoginOpen(false); }} />
  </div>;
}

import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, FileHeart, ChevronRight } from 'lucide-react';
import { ApiError, getCurrentCustomer, getTcmReportConsent, updateTcmReportConsent, type TcmReportConsent } from '../api';
import { clearCustomerAuth, CUSTOMER_SESSION_REFRESH_INTERVAL_MS, isCustomerAuthTokenActive, readCustomerAuth, writeCustomerAuth, type CustomerAuth } from '../customerAuth';
import { maskedPhone } from '../profile';
import { ensureReportConsent, openOriginalReport, resolveReportEntry, TCM_REPORT_VIEW_NOTICE } from '../tcmReports';
import MyReports from './MyReports';
import RecordLoginDialog from './RecordLoginDialog';
import ReportViewNotice from './ReportViewNotice';

export default function ReportEntryPage() {
  const [auth, setAuth] = useState<CustomerAuth | null>(readCustomerAuth);
  const [loginOpen, setLoginOpen] = useState(() => !readCustomerAuth());
  const [consent, setConsent] = useState<TcmReportConsent | null>(null);
  const [history, setHistory] = useState(false);
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(() => Boolean(readCustomerAuth()));
  const [message, setMessage] = useState('');
  const controller = useRef<AbortController | null>(null);
  const running = useRef(false);
  const explicitLogin = useRef(false);
  const navigationType = (window.performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined)?.type;
  const returnedFromReport = useRef(Boolean(window.history.state?.hxy_report_original_opened) && navigationType !== 'navigate' && navigationType !== 'reload');

  function clearView() {
    controller.current?.abort();
    running.current = false;
    setBusy(false); setChecking(false); setConsent(null); setHistory(false); setMessage('');
  }

  function verifyNumber(note = '') {
    explicitLogin.current = false; returnedFromReport.current = false;
    clearView(); clearCustomerAuth(); setAuth(null); setLoginOpen(true); setMessage(note);
  }

  function finishEntry(result: Awaited<ReturnType<typeof resolveReportEntry>>) {
    setConsent(result.consent);
    if (result.kind === 'ready') {
      window.history.replaceState({ ...window.history.state, hxy_report_original_opened: true }, '');
      openOriginalReport(result.url);
    } else setMessage(result.kind === 'action-required' ? '当前会话尚无有效的本人报告查看记录，请阅读说明后点击“查看本人报告”。' : result.kind === 'empty' ? '还没有检测报告。已做过检测？请确认登录的是检测时登记的手机号；未检测可到店联系前台。' : '检测时间未提供或无法确定最近一次，请在历史报告中选择。');
  }

  function showError(reason: unknown) {
    if (reason instanceof ApiError && (reason.status === 401 || reason.code === 'PHONE_VERIFICATION_REQUIRED')) {
      verifyNumber(reason.status === 401 ? '登录已过期，请重新登录。' : '请验证检测时登记的手机号。');
      return;
    }
    if (reason instanceof ApiError && reason.code === 'TCM_CONSENT_REQUIRED') {
      setConsent(value => value ? { ...value, consented: false } : null);
      setHistory(false);
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
    let refreshing = false;
    setChecking(true);
    async function refreshIdentity() {
      if (!active || refreshing || identityController.signal.aborted) return false;
      refreshing = true;
      try {
        if (!isCustomerAuthTokenActive(token)) throw new ApiError(401, '登录已过期');
        const user = await getCurrentCustomer(token);
        if (!active || identityController.signal.aborted) return false;
        if (user.id !== auth!.user.id || user.phone !== auth!.user.phone) throw new ApiError(401, '登录号码已更新');
        writeCustomerAuth({ token, user });
        return true;
      } catch (reason) { if (active && !identityController.signal.aborted) showError(reason); return false; }
      finally { refreshing = false; }
    }
    async function enter() {
      try {
        if (!await refreshIdentity() || !active || entryController.signal.aborted) return;
        const status = await getTcmReportConsent(token, entryController.signal);
        if (!active || entryController.signal.aborted) return;
        setConsent(status);
        if (returnedFromReport.current) { setMessage('报告已打开，可再次查看或选择历史报告。'); return; }
        const result = await resolveReportEntry(token, status, explicitLogin.current ? TCM_REPORT_VIEW_NOTICE : null, entryController.signal);
        if (active && !entryController.signal.aborted) finishEntry(result);
      } catch (reason) { if (active && !entryController.signal.aborted) showError(reason); }
      finally { if (active && !entryController.signal.aborted) { explicitLogin.current = false; setChecking(false); } }
    }
    void enter();
    const whenVisible = () => { if (document.visibilityState === 'visible') void refreshIdentity(); };
    const timer = window.setInterval(whenVisible, CUSTOMER_SESSION_REFRESH_INTERVAL_MS);
    window.addEventListener('focus', whenVisible);
    document.addEventListener('visibilitychange', whenVisible);
    return () => {
      active = false; identityController.abort(); entryController.abort(); controller.current?.abort();
      window.clearInterval(timer);
      window.removeEventListener('focus', whenVisible);
      document.removeEventListener('visibilitychange', whenVisible);
    };
  }, [auth?.token]);

  async function viewReport(kind: 'latest' | 'history') {
    if (!auth || !consent || running.current || checking) return;
    const current = new AbortController();
    controller.current?.abort(); controller.current = current; running.current = true;
    setBusy(true); setMessage('');
    try {
      const status = await getTcmReportConsent(auth.token, current.signal);
      if (current.signal.aborted) return;
      setConsent(status);
      if (kind === 'history') {
        if (!status.consented) { setMessage('请阅读说明后点击“查看本人报告”。'); return; }
        await ensureReportConsent(auth.token, status, current.signal);
        if (!current.signal.aborted) setHistory(true);
        return;
      }
      const result = await resolveReportEntry(auth.token, status, consent.notice, current.signal);
      if (current.signal.aborted) return;
      finishEntry(result);
    } catch (reason) { if (!current.signal.aborted) showError(reason); }
    finally { if (!current.signal.aborted) { running.current = false; setBusy(false); } }
  }

  async function revoke() {
    if (!auth) return;
    clearView();
    const current = new AbortController(); controller.current = current;
    running.current = true; setBusy(true);
    try {
      const status = await updateTcmReportConsent(auth.token, null, current.signal);
      if (!current.signal.aborted) setConsent(status);
    } catch (reason) { if (!current.signal.aborted) showError(reason); }
    finally { if (!current.signal.aborted) { running.current = false; setBusy(false); } }
  }

  return <div className="report-entry-page">
    <header><button type="button" aria-label="返回" onClick={() => { if (history) setHistory(false); else { clearView(); window.history.back(); } }}><ArrowLeft size={22} /></button><strong>{history ? '历史报告' : '我的检测报告'}</strong><span /></header>
    <main>
      {history && auth ? <MyReports key={auth.token} token={auth.token} onVerify={() => verifyNumber()} showActionLabel onConsentRequired={() => { setHistory(false); setConsent(value => value ? { ...value, consented: false } : null); setMessage('报告查看授权已撤回，请阅读说明后重新点击查看。'); }} /> : <>
        <section className="report-entry-intro"><FileHeart size={32} strokeWidth={1.5} aria-hidden="true" /><h1>我的检测报告</h1><p>查看最近一次检测结果</p></section>
        {auth && <div className="report-entry-account"><span>{maskedPhone(auth.user.phone)}</span><button type="button" onClick={() => verifyNumber()}>换个号码</button></div>}
        {(checking || busy) && <p role="status">正在打开本人报告…</p>}
        {message && <p className="report-entry-message" role="alert">{message}</p>}
        {!auth ? <button className="report-entry-primary" type="button" onClick={() => setLoginOpen(true)}>登录并查看报告<ChevronRight size={18} aria-hidden="true" /></button> : <>
          {consent && !checking && !busy && <ReportViewNotice notice={consent.notice} actionLabel={!consent.consented ? '查看本人报告' : undefined} />}
          {consent && !checking && !busy && <button className="report-entry-primary" type="button" onClick={() => void viewReport('latest')}>{consent.consented ? '再次查看报告' : '查看本人报告'}<ChevronRight size={18} aria-hidden="true" /></button>}
          {consent?.consented && !checking && !busy && <>
            <button className="report-entry-history" type="button" onClick={() => void viewReport('history')}>历史报告</button>
            <button className="report-entry-revoke" type="button" onClick={() => void revoke()}>撤回DIY报告查看授权</button>
          </>}
          {!consent && !checking && <button className="report-entry-history" type="button" onClick={() => window.location.reload()}>重新检查</button>}
        </>}
      </>}
    </main>
    <RecordLoginDialog key={loginOpen ? 'login' : 'closed'} open={loginOpen} selectionSessionId="" selectionToken="" purpose="report" notice={message} onClose={() => setLoginOpen(false)} onSuccess={next => { explicitLogin.current = true; returnedFromReport.current = false; clearView(); setAuth(next); setLoginOpen(false); }} />
  </div>;
}

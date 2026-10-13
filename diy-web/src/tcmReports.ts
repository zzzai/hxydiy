import type { TcmReportSummary } from './api';
import { getTcmReport, getTcmReports, updateTcmReportConsent, type TcmReportConsent } from './api.ts';

export const TCM_REPORT_VIEW_NOTICE = '我单独同意使用已验证手机号查询本人健康检测报告，并在有有效来源链接时跳转到检测方原站查看完整报告。完整报告可能包含个人及健康信息，以原站展示为准；DIY不向原站传递我的手机号、登录令牌或读取密钥，不复制报告图片，也不向店员开放、不用于推送或新增诊断。原站链接无需原站登录即可打开，获得链接的人可能查看报告，请勿转发。我可撤回DIY报告查看授权，但撤回不能使已经获得的原站链接失效，也不能阻止他人打开已转发的链接。';

export function verifiedOriginalReportUrl(value: string | null, reportId: string): string | null {
  if (!value || value.length > 4096 || !value.startsWith('https://yk.qianmaitcm.com/print_smart_healthcare/#/discriminateRingReport?') || /[\x00-\x20\x7f\\]/.test(value) || !/^[A-Za-z0-9_-]{1,128}$/.test(reportId)) return null;
  try {
    const url = new URL(value);
    const [route, query] = url.hash.slice(1).split('?');
    const params = new URLSearchParams(query);
    if (url.origin !== 'https://yk.qianmaitcm.com' || url.username || url.password || url.pathname !== '/print_smart_healthcare/' || url.search || route !== '/discriminateRingReport' || [...params].length !== 1 || params.get('reportId') !== reportId) return null;
    return value;
  } catch { return null; }
}

export function reportsByDate(items: TcmReportSummary[]): TcmReportSummary[] {
  return [...items].sort((a, b) => {
    const first = a.reported_at ? Date.parse(a.reported_at) : -Infinity;
    const second = b.reported_at ? Date.parse(b.reported_at) : -Infinity;
    return second === first ? 0 : second > first ? 1 : -1;
  });
}

export async function ensureReportConsent(token: string, status: TcmReportConsent, signal: AbortSignal): Promise<TcmReportConsent> {
  signal.throwIfAborted();
  if (status.version !== 'tcm-report-access-v2-original' || !status.notice.trim()) throw new Error('报告查看说明已更新，请刷新后重新查看。');
  const result = status.consented ? status : await updateTcmReportConsent(token, status.version, signal);
  signal.throwIfAborted();
  if (!result.consented) throw new Error('暂时无法确认本人报告查看，请重试。');
  return result;
}

export async function originalReportUrl(token: string, reportId: string, signal: AbortSignal): Promise<string> {
  signal.throwIfAborted();
  const result = await getTcmReport(token, reportId, signal);
  signal.throwIfAborted();
  const url = result.report_id === reportId ? verifiedOriginalReportUrl(result.original_report_url, reportId) : null;
  if (!url) throw new Error('完整报告地址暂不可用，请稍后重试或联系门店。');
  return url;
}

export function openOriginalReport(url: string) {
  const link = document.createElement('a');
  link.href = url; link.target = '_self'; link.rel = 'noopener noreferrer'; link.referrerPolicy = 'no-referrer';
  link.click();
}

export async function latestOriginalReport(token: string, signal: AbortSignal): Promise<{ kind: 'ready'; url: string } | { kind: 'empty' | 'choose' }> {
  const items = new Map<string, TcmReportSummary>();
  let offset = 0;
  while (true) {
    signal.throwIfAborted();
    const page = await getTcmReports(token, offset, signal);
    signal.throwIfAborted();
    for (const item of page.items) items.set(item.report_id, item);
    if (!page.has_more) break;
    if (!page.items.length || page.offset !== offset || !Number.isSafeInteger(page.limit) || page.limit <= 0 || offset + page.limit > 100000) throw new Error('报告列表暂时不完整，请稍后重试。');
    offset += page.limit;
  }
  if (!items.size) return { kind: 'empty' };
  const sorted = reportsByDate([...items.values()]);
  if (sorted.some(item => !item.reported_at || !Number.isFinite(Date.parse(item.reported_at))) || sorted.length > 1 && Date.parse(sorted[0].reported_at!) === Date.parse(sorted[1].reported_at!)) return { kind: 'choose' };
  return { kind: 'ready', url: await originalReportUrl(token, sorted[0].report_id, signal) };
}

export async function resolveReportEntry(token: string, status: TcmReportConsent, displayedNotice: string | null, signal: AbortSignal) {
  signal.throwIfAborted();
  if (status.version !== 'tcm-report-access-v2-original' || !status.consented && (displayedNotice === null || displayedNotice !== status.notice)) return { kind: 'action-required' as const, consent: status };
  const consent = await ensureReportConsent(token, status, signal);
  const result = await latestOriginalReport(token, signal);
  signal.throwIfAborted();
  return { ...result, consent };
}

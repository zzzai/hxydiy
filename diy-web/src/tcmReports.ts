import type { TcmReportSummary } from './api';
import { getTcmReport, getTcmReports } from './api.ts';

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

export function shouldAutoOpenReport(state: { hxy_report_original_opened?: boolean } | null, navigationType?: string): boolean {
  return !state?.hxy_report_original_opened || navigationType === 'reload';
}

export async function loadReportIndex(token: string, signal: AbortSignal): Promise<TcmReportSummary[]> {
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
  return reportsByDate([...items.values()]);
}

export async function latestOriginalReport(token: string, signal: AbortSignal): Promise<{ kind: 'ready'; url: string } | { kind: 'empty' | 'choose' }> {
  const sorted = await loadReportIndex(token, signal);
  if (!sorted.length) return { kind: 'empty' };
  if (sorted.some(item => !item.reported_at || !Number.isFinite(Date.parse(item.reported_at))) || sorted.length > 1 && Date.parse(sorted[0].reported_at!) === Date.parse(sorted[1].reported_at!)) return { kind: 'choose' };
  return { kind: 'ready', url: await originalReportUrl(token, sorted[0].report_id, signal) };
}

export async function resolveReportEntry(token: string, signal: AbortSignal) {
  return latestOriginalReport(token, signal);
}

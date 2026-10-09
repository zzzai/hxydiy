import type { TcmReportSummary } from './api';

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

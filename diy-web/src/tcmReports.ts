import type { TcmReportSummary } from './api';

export function reportsByDate(items: TcmReportSummary[]): TcmReportSummary[] {
  return [...items].sort((a, b) => {
    const first = a.reported_at ? Date.parse(a.reported_at) : -Infinity;
    const second = b.reported_at ? Date.parse(b.reported_at) : -Infinity;
    return second === first ? 0 : second > first ? 1 : -1;
  });
}

import assert from 'node:assert/strict';
import test from 'node:test';
import { reportsByDate } from '../src/tcmReports.ts';

test('personal reports use detection time descending, missing time last, without changing source results', () => {
  const items = [
    { report_id: 'unknown', reported_at: null, title: '检测报告' as const },
    { report_id: 'early', reported_at: '2026-10-01T10:00:00+08:00', title: '检测报告' as const },
    { report_id: 'later', reported_at: '2026-10-02T10:00:00+08:00', title: '检测报告' as const },
  ];
  assert.deepEqual(reportsByDate(items).map(item => item.report_id), ['later', 'early', 'unknown']);
  assert.equal(items[0].report_id, 'unknown');
});

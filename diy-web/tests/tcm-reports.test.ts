import assert from 'node:assert/strict';
import test from 'node:test';
import { reportsByDate, verifiedOriginalReportUrl } from '../src/tcmReports.ts';

test('personal reports use detection time descending, missing time last, without changing source results', () => {
  const items = [
    { report_id: 'unknown', reported_at: null, title: '检测报告' as const },
    { report_id: 'early', reported_at: '2026-10-01T10:00:00+08:00', title: '检测报告' as const },
    { report_id: 'later', reported_at: '2026-10-02T10:00:00+08:00', title: '检测报告' as const },
  ];
  assert.deepEqual(reportsByDate(items).map(item => item.report_id), ['later', 'early', 'unknown']);
  assert.equal(items[0].report_id, 'unknown');
});

test('original report links require the fixed source and matching verified report ID', () => {
  const valid = 'https://yk.qianmaitcm.com/print_smart_healthcare/#/discriminateRingReport?reportId=OWN-1';
  assert.equal(verifiedOriginalReportUrl(valid, 'OWN-1'), valid);
  for (const value of [null, valid.replace('https:', 'http:'), valid.replace('.com/', '.com:443/'), valid.replace('yk.qianmaitcm.com', 'evil.example'), valid + '&extra=1', valid + '&reportId=OWN-1', valid.replace('OWN-1', 'OTHER-1'), 'javascript:alert(1)']) {
    assert.equal(verifiedOriginalReportUrl(value, 'OWN-1'), null);
  }
});

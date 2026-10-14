import assert from 'node:assert/strict';
import test from 'node:test';
import * as entry from '../src/returnEntry.ts';
import * as reports from '../src/tcmReports.ts';

test('explicit legacy return is a report task while bare return and QR priorities stay unchanged', () => {
  assert.equal(entry.isReportEntry(new URLSearchParams('store=1&view=return&seat=old&token=old')), true);
  assert.equal(entry.isReportEntry(new URLSearchParams('store=1')), false);
  for (const value of ['seat=sofa-01&qr=signed', 'project=hxy-qiqing-30', 'source=kiosk', 'view=menu']) assert.equal(entry.isReportEntry(new URLSearchParams(value)), false);
});

test('bare return stays a return task across canonicalization and repeated parsing; explicit return stays reports', () => {
  let url = new URL('https://synthetic.invalid/?store=1');
  for (let parse = 0; parse < 3; parse++) {
    assert.equal(entry.isReturnEntry(url.searchParams), true);
    assert.equal(entry.isReportEntry(url.searchParams), false);
    assert.equal(entry.isServiceAccountEntry(url.searchParams), false);
    url = new URL(entry.stableStoreEntry(url.origin, 1, null));
    assert.deepEqual([...url.searchParams], [['store', '1']]);
  }
  const explicit = new URL(entry.stableStoreEntry(url.origin, 1));
  assert.equal(explicit.searchParams.get('view'), 'return');
  assert.equal(entry.isReportEntry(explicit.searchParams), true);
  assert.equal(entry.isReportEntry(new URLSearchParams('store=1&view=reports')), true);
});

test('browser Back opens the report center, while a deliberate refresh may retry direct entry', () => {
  assert.equal(typeof reports.shouldAutoOpenReport, 'function');
  assert.equal(reports.shouldAutoOpenReport({ hxy_report_original_opened: true }, 'back_forward'), false);
  assert.equal(reports.shouldAutoOpenReport({ hxy_report_original_opened: true }, 'navigate'), false);
  assert.equal(reports.shouldAutoOpenReport({ hxy_report_original_opened: true }, 'reload'), true);
  assert.equal(reports.shouldAutoOpenReport(null, 'navigate'), true);
});

test('a direct entry never treats the initial blank tab or later original-report entry as its parent', () => {
  assert.equal(typeof entry.reportEntryHasBack, 'function');
  assert.equal(entry.reportEntryHasBack(null, 2, ''), false);
  assert.equal(entry.reportEntryHasBack(null, 2, 'https://diy.hexiaoyue.com/?store=1&view=menu'), true);
  assert.equal(entry.reportEntryHasBack({ hxy_report_entry_back: false }, 3, ''), false);
  assert.equal(entry.reportEntryHasBack({ hxy_report_entry_back: true }, 3, ''), true);
});

test('report center reads an owned index without granting consent or opening provider details', async () => {
  assert.equal(typeof reports.loadReportIndex, 'function');
  const oldFetch = globalThis.fetch;
  const calls: string[] = [];
  globalThis.fetch = (async (url: string) => {
    calls.push(String(url));
    return Response.json({ items: [{ report_id: 'OLD', reported_at: '2026-10-01T10:00:00+08:00', title: '检测报告' }, { report_id: 'NEW', reported_at: '2026-10-14T10:00:00+08:00', title: '检测报告' }], offset: 0, limit: 20, has_more: false });
  }) as typeof fetch;
  try {
    assert.deepEqual((await reports.loadReportIndex('synthetic', new AbortController().signal)).map(item => item.report_id), ['NEW', 'OLD']);
    assert.deepEqual(calls, ['/api/v1/me/tcm-reports?limit=20&offset=0']);
  } finally { globalThis.fetch = oldFetch; }
});

test('report links allow only store and dedicated view without old credentials', () => {
  assert.equal(typeof entry.reportEntryUrl, 'function');
  const url = new URL(entry.reportEntryUrl('https://diy.hexiaoyue.com/?seat=old&token=secret#report', 1));
  assert.deepEqual([...url.searchParams], [['store', '1'], ['view', 'reports']]);
  assert.equal(url.hash, '');
});

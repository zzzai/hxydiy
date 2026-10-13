import assert from 'node:assert/strict';
import test from 'node:test';
import * as reports from '../src/tcmReports.ts';
import { isReportEntry, isReturnEntry, isServiceAccountEntry } from '../src/returnEntry.ts';

test('the dedicated report intent does not enter arrival or return flows', () => {
  assert.equal(isReturnEntry(new URLSearchParams('view=reports')), false);
  assert.equal(isServiceAccountEntry(new URLSearchParams('view=reports&seat=sofa-01&qr=old')), false);
  assert.equal(isReportEntry(new URLSearchParams('view=reports&seat=sofa-01&qr=old&session=old&project=old&source=kiosk')), true);
  for (const query of ['view=return', 'view=menu', 'seat=sofa-01&source=store_qr', 'qr=signed']) assert.equal(isReportEntry(new URLSearchParams(query)), false);
});

const api = reports as unknown as {
  ensureReportConsent: (token: string, status: { consented: boolean; version: string; notice: string }, signal: AbortSignal) => Promise<unknown>;
  latestOriginalReport: (token: string, signal: AbortSignal) => Promise<{ kind: string; url?: string }>;
  resolveReportEntry: (token: string, status: { consented: boolean; version: string; notice: string }, displayedNotice: string | null, signal: AbortSignal) => Promise<{ kind: string; url?: string; consent: { consented: boolean } }>;
};
const status = { consented: false, version: 'tcm-report-access-v2-original', notice: 'Synthetic notice' };
const row = (id: string, date: string | null) => ({ report_id: id, reported_at: date, title: '检测报告' });
const page = (items: ReturnType<typeof row>[], offset = 0, has_more = false) => ({ items, offset, limit: 20, has_more });
const detail = (id: string, url: string | null = `https://yk.qianmaitcm.com/print_smart_healthcare/#/discriminateRingReport?reportId=${id}`) => ({ ...row(id, '2026-10-13T10:00:00+08:00'), original_report_url: url, physiques: [], heart_rate: null, blood_oxygen: null, moisture: null });

async function withApi(responses: Array<unknown>, action: (calls: Array<{ path: string; options: RequestInit }>) => Promise<void>) {
  const original = globalThis.fetch;
  const calls: Array<{ path: string; options: RequestInit }> = [];
  globalThis.fetch = (async (path, options = {}) => {
    calls.push({ path: String(path), options });
    const result = responses.shift();
    assert.notEqual(result, undefined, 'Unexpected API call');
    return result instanceof Response ? result : Response.json(result);
  }) as typeof fetch;
  try { await action(calls); } finally { globalThis.fetch = original; }
}

test('an explicit first view grants only current self consent; valid consent is reused', async () => {
  assert.equal(typeof api.ensureReportConsent, 'function');
  await withApi([{ ...status, consented: true }], async calls => {
    await api.ensureReportConsent('synthetic-token', status, new AbortController().signal);
    assert.equal(calls[0].path, '/api/v1/me/tcm-report-consent');
    assert.equal(calls[0].options.method, 'POST');
    assert.deepEqual(JSON.parse(String(calls[0].options.body)), { accepted: true, version: 'tcm-report-access-v2-original' });
    await api.ensureReportConsent('synthetic-token', { ...status, consented: true }, new AbortController().signal);
    assert.equal(calls.length, 1);
  });
});

test('unknown consent versions and failed consent never permit a report query', async () => {
  await withApi([], async calls => {
    await assert.rejects(api.ensureReportConsent('token', { ...status, version: 'old-v1' }, new AbortController().signal), /说明已更新/);
    assert.equal(calls.length, 0);
  });
  await withApi([Response.json({ detail: 'Synthetic failure' }, { status: 503 })], async calls => {
    await assert.rejects(api.ensureReportConsent('token', status, new AbortController().signal));
    assert.equal(calls.length, 1);
    assert.equal(calls[0].path, '/api/v1/me/tcm-report-consent');
  });
});

test('abort after a late list response prevents detail reads', async () => {
  const originalFetch = globalThis.fetch;
  const controller = new AbortController();
  let calls = 0;
  globalThis.fetch = (async () => { calls++; controller.abort(); return Response.json(page([row('NEW', '2026-10-13T10:00:00+08:00')])); }) as typeof fetch;
  try {
    await assert.rejects(api.latestOriginalReport('token', controller.signal), { name: 'AbortError' });
    assert.equal(calls, 1);
  } finally { globalThis.fetch = originalFetch; }
});

test('latest report is selected by verified dates across pages, then its detail URL is checked', async () => {
  assert.equal(typeof api.latestOriginalReport, 'function');
  await withApi([page([row('OLD', '2026-10-01T10:00:00+08:00')], 0, true), page([row('NEW', '2026-10-13T10:00:00+08:00')], 20), detail('NEW')], async calls => {
    const result = await api.latestOriginalReport('synthetic-token', new AbortController().signal);
    assert.deepEqual(result, { kind: 'ready', url: 'https://yk.qianmaitcm.com/print_smart_healthcare/#/discriminateRingReport?reportId=NEW' });
    assert.deepEqual(calls.map(call => call.path), ['/api/v1/me/tcm-reports?limit=20&offset=0', '/api/v1/me/tcm-reports?limit=20&offset=20', '/api/v1/me/tcm-reports/NEW']);
    assert.ok(calls.every(call => call.options.cache === 'no-store'));
  });
});

test('empty reports and unknown dates never invent a latest report', async () => {
  assert.equal(typeof api.latestOriginalReport, 'function');
  for (const [items, kind] of [[[], 'empty'], [[row('UNKNOWN', null), row('KNOWN', '2026-10-13T10:00:00+08:00')], 'choose']] as const) {
    await withApi([page([...items])], async calls => {
      assert.equal((await api.latestOriginalReport('token', new AbortController().signal)).kind, kind);
      assert.equal(calls.length, 1);
    });
  }
});

test('a single dated report opens directly while tied dates require a choice', async () => {
  await withApi([page([row('SINGLE', '2026-10-13T10:00:00+08:00')]), detail('SINGLE')], async calls => {
    assert.equal((await api.latestOriginalReport('token', new AbortController().signal)).kind, 'ready');
    assert.equal(calls.length, 2);
  });
  await withApi([page([row('A', '2026-10-13T10:00:00+08:00'), row('B', '2026-10-13T10:00:00+08:00')])], async calls => {
    assert.equal((await api.latestOriginalReport('token', new AbortController().signal)).kind, 'choose');
    assert.equal(calls.length, 1);
  });
});

test('a missing or mismatched newest link does not fall back to an older report', async () => {
  assert.equal(typeof api.latestOriginalReport, 'function');
  for (const invalid of [detail('NEW', null), detail('OTHER'), detail('NEW', 'https://evil.example/report')]) {
    await withApi([page([row('OLD', '2026-10-01T10:00:00+08:00'), row('NEW', '2026-10-13T10:00:00+08:00')]), invalid], async calls => {
      await assert.rejects(api.latestOriginalReport('token', new AbortController().signal), /地址暂不可用/);
      assert.equal(calls.at(-1)?.path, '/api/v1/me/tcm-reports/NEW');
      assert.equal(calls.length, 2);
    });
  }
});

test('expired identity and consent failures stop before detail reads', async () => {
  assert.equal(typeof api.latestOriginalReport, 'function');
  for (const code of [401, 403, 503]) {
    await withApi([Response.json({ detail: { message: 'Synthetic failure' } }, { status: code })], async calls => {
      await assert.rejects(api.latestOriginalReport('token', new AbortController().signal));
      assert.equal(calls.length, 1);
    });
  }
});

test('cancelled navigation cannot consume a late report response', async () => {
  assert.equal(typeof api.latestOriginalReport, 'function');
  const controller = new AbortController();
  controller.abort();
  await withApi([], async calls => {
    await assert.rejects(api.latestOriginalReport('token', controller.signal), { name: 'AbortError' });
    assert.equal(calls.length, 0);
  });
});

test('original report navigation stays in the same window without referrer or credentials', () => {
  const original = globalThis.document;
  const link = { href: '', target: '', rel: '', referrerPolicy: '', click() { clicked = true; } };
  let clicked = false;
  Object.defineProperty(globalThis, 'document', { configurable: true, value: { createElement: () => link } });
  try {
    reports.openOriginalReport('https://yk.qianmaitcm.com/print_smart_healthcare/#/discriminateRingReport?reportId=SYNTH-1');
    assert.equal(link.href, 'https://yk.qianmaitcm.com/print_smart_healthcare/#/discriminateRingReport?reportId=SYNTH-1');
    assert.equal(link.target, '_self');
    assert.equal(link.referrerPolicy, 'no-referrer');
    assert.equal(link.rel, 'noopener noreferrer');
    assert.equal(clicked, true);
  } finally { Object.defineProperty(globalThis, 'document', { configurable: true, value: original }); }
});

test('combined login and view continues directly through self consent to the newest original', async () => {
  assert.equal(typeof api.resolveReportEntry, 'function');
  await withApi([{ ...status, consented: true }, page([row('NEW', '2026-10-13T10:00:00+08:00')]), detail('NEW')], async calls => {
    const result = await api.resolveReportEntry('token', status, 'Synthetic notice', new AbortController().signal);
    assert.equal(result.kind, 'ready');
    assert.ok(result.url?.endsWith('reportId=NEW'));
    assert.equal(result.consent.consented, true);
    assert.deepEqual(calls.map(call => [call.options.method || 'GET', call.path]), [['POST', '/api/v1/me/tcm-report-consent'], ['GET', '/api/v1/me/tcm-reports?limit=20&offset=0'], ['GET', '/api/v1/me/tcm-reports/NEW']]);
  });
});

test('an existing verified v2 session enters its report without another view action or grant POST', async () => {
  assert.equal(typeof api.resolveReportEntry, 'function');
  await withApi([page([row('NEW', '2026-10-13T10:00:00+08:00')]), detail('NEW')], async calls => {
    const result = await api.resolveReportEntry('token', { ...status, consented: true }, null, new AbortController().signal);
    assert.equal(result.kind, 'ready');
    assert.ok(calls.every(call => (call.options.method || 'GET') === 'GET'));
  });
});

test('an existing session with missing, old or revoked consent never grants on page entry', async () => {
  assert.equal(typeof api.resolveReportEntry, 'function');
  await withApi([], async calls => {
    for (const version of ['tcm-report-access-v2-original', 'tcm-report-access-v1']) {
      assert.equal((await api.resolveReportEntry('token', { ...status, version }, null, new AbortController().signal)).kind, 'action-required');
    }
    assert.equal(calls.length, 0);
  });
});

test('a changed notice cannot silently reuse the combined login intent', async () => {
  assert.equal(typeof api.resolveReportEntry, 'function');
  await withApi([], async calls => {
    assert.equal((await api.resolveReportEntry('token', { ...status, notice: 'Changed notice' }, 'Synthetic notice', new AbortController().signal)).kind, 'action-required');
    assert.equal(calls.length, 0);
  });
});

test('a failed combined-view consent stops before listing or opening any report', async () => {
  assert.equal(typeof api.resolveReportEntry, 'function');
  await withApi([Response.json({ detail: 'Synthetic consent failure' }, { status: 503 })], async calls => {
    await assert.rejects(api.resolveReportEntry('token', status, 'Synthetic notice', new AbortController().signal));
    assert.equal(calls.length, 1);
    assert.equal(calls[0].path, '/api/v1/me/tcm-report-consent');
  });
});

test('cancelled automatic entry does not grant, list or navigate', async () => {
  assert.equal(typeof api.resolveReportEntry, 'function');
  const controller = new AbortController(); controller.abort();
  await withApi([], async calls => {
    await assert.rejects(api.resolveReportEntry('token', status, 'Synthetic notice', controller.signal), { name: 'AbortError' });
    assert.equal(calls.length, 0);
  });
});

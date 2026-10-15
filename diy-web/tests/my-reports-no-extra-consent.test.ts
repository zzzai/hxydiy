import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import ts from 'typescript';
import * as api from '../src/api.ts';
import * as reports from '../src/tcmReports.ts';
import * as profile from '../src/profile.ts';

test('profile report fallback loads reports without consent probes or writes', async () => {
  const source = ts.transpileModule(fs.readFileSync(new URL('../src/components/MyReports.tsx', import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const effects: Array<() => void | (() => void)> = [];
  const changes: unknown[] = [];
  const paths: string[] = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (path: string) => {
    paths.push(String(path));
    if (String(path).endsWith('/tcm-report-consent')) return Response.json({ consented: false, version: 'tcm-report-access-v2-original', notice: 'Legacy fixture' });
    if (String(path) === '/api/v1/me/tcm-reports?limit=20&offset=0') return Response.json({ items: [{ report_id: 'OWN', title: '检测报告', reported_at: null }], limit: 20, offset: 0, has_more: false });
    throw new Error('Unexpected report operation');
  }) as typeof fetch;
  const modules: Record<string, unknown> = {
    react: {
      useRef: (value: unknown) => ({ current: value }),
      useState: (value: unknown) => [value, (next: unknown) => changes.push(next)],
      useEffect: (effect: () => void | (() => void)) => effects.push(effect),
    },
    'react/jsx-runtime': { jsx: (_type: unknown, props: unknown) => props, jsxs: (_type: unknown, props: unknown) => props },
    'lucide-react': {}, '../api': api, '../tcmReports': reports, '../profile': profile,
  };
  const exports: { default?: (props: unknown) => unknown } = {};
  const events = { addEventListener() {}, removeEventListener() {} };
  const context = vm.createContext({ exports, AbortController, setTimeout, clearTimeout,
    document: { ...events, visibilityState: 'visible' }, window: events,
    require: (name: string) => { if (!(name in modules)) throw new Error('Unexpected dependency'); return modules[name]; },
  });
  const cleanups: Array<() => void> = [];
  try {
    new vm.Script(source).runInContext(context);
    exports.default!({ token: 'verified-fixture', onVerify() {} });
    for (const effect of effects) { const cleanup = effect(); if (cleanup) cleanups.push(cleanup); }
    for (let turn = 0; turn < 12; turn++) await new Promise<void>(resolve => setImmediate(resolve));
    assert.deepEqual(paths, ['/api/v1/me/tcm-reports?limit=20&offset=0']);
    assert.ok(changes.some(value => typeof value === 'object' && value !== null && 'items' in value));
  } finally { cleanups.forEach(cleanup => cleanup()); globalThis.fetch = originalFetch; }
});

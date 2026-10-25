import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { build } from 'esbuild';

const root = fileURLToPath(new URL('../../', import.meta.url));
const runtimeRequire = createRequire(import.meta.url);
const React = runtimeRequire('react');
const { create, act } = runtimeRequire('react-test-renderer');
const runtime = await mkdtemp(path.join(tmpdir(), 'hxy-private-selection-test-'));
const bundle = path.join(runtime, 'app-under-test.cjs');
let App;
try {
  await build({
    entryPoints: [path.join(root, 'diy-web/src/App.tsx')], outfile: bundle,
    bundle: true, platform: 'node', format: 'cjs', jsx: 'automatic',
    define: { 'import.meta.env': '{}' },
    plugins: [{
      name: 'same-react-runtime-and-animation-layout',
      setup(build) {
        build.onResolve({ filter: /^react(\/.*)?$/ }, args => ({ path: runtimeRequire.resolve(args.path), external: true }));
        build.onResolve({ filter: /^framer-motion$/ }, () => ({ path: 'motion', namespace: 'animation-test' }));
        build.onLoad({ filter: /.*/, namespace: 'animation-test' }, () => ({
          loader: 'js',
          contents: "const React = require('react'); const types = new Map(); export const motion = new Proxy({}, { get: (_, type) => { if (!types.has(type)) types.set(type, React.forwardRef((props, ref) => React.createElement(type, {...props, ref}))); return types.get(type); } }); export const AnimatePresence = ({children}) => children;",
        }));
      },
    }],
  });
  App = runtimeRequire(bundle).default;
} finally {
  await rm(runtime, { recursive: true, force: true });
}

const privateKey = 'hxy_diy_private_selection_1';
const authKey = 'hxy_diy_customer_auth';
const project = {
  id: 1, code: 'hxy-qiqing-30', name: 'Synthetic project', category: 'bath',
  category_mark: '泡', duration_min: 30, summary: '', image_url: '', tags: [], price_label: '',
  prices: [{ price_type: 'store', amount_cents: 2990 }, { price_type: 'member', amount_cents: 2590 }],
};
const selectedItems = [{ project_id: 1, item_type: 'service', quantity: 1, chargeable: true, diy_preferences: ['适中'], addon_ids: [] }];
const session = (id, status = 'draft') => ({
  id, store_id: 1, source: 'in_store', device_label: 'synthetic', status,
  items: selectedItems, pricing_snapshot: {}, store_total_cents: 2990, member_total_cents: 2590,
  expires_at: null, submitted_at: status === 'draft' ? null : '2026-10-17T00:00:00Z', cart_version: 0,
});
const auth = id => ({
  token: 'test.' + Buffer.from(JSON.stringify({ exp: 4102444800, sub: id })).toString('base64url') + '.synthetic',
  user: { id, openid: 'synthetic-' + id, phone: '', nickname: 'Synthetic', is_member: false, member_type: null, balance_cents: 0 },
});
const record = (id = 'anonymous-draft', customerId = null) => ({
  storeId: 1, customerId, sessionId: id, accessToken: id + '-owner', items: selectedItems,
});
const deferred = () => {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
};
const response = data => ({ ok: true, status: 200, json: async () => data });
const settle = async () => {
  for (let index = 0; index < 4; index++) await act(async () => { await new Promise(done => setImmediate(done)); });
};
function environment(url, values = new Map()) {
  const storage = {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: key => values.delete(key),
  };
  const location = new URL(url);
  const timers = new Set();
  const intervals = new Map();
  const timeouts = new Map();
  const listeners = new Map();
  const timeout = (fn, delay) => {
    const handle = setTimeout(() => { timeouts.delete(handle); fn(); }, delay);
    handle.unref();
    timers.add(handle);
    timeouts.set(handle, { fn, delay });
    return handle;
  };
  const history = { state: null, replaceState(state, _title, next) { this.state = state; if (next) location.href = String(new URL(next, location)); }, pushState(state, _title, next) { this.replaceState(state, _title, next); }, back() {} };
  globalThis.localStorage = storage;
  globalThis.sessionStorage = { ...storage, getItem: () => null, setItem() {}, removeItem() {} };
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { onLine: true, userAgent: 'Synthetic React test' } });
  globalThis.document = { visibilityState: 'visible', title: '', addEventListener() {}, removeEventListener() {}, querySelector: () => null, querySelectorAll: () => [], getElementById: () => null, body: { style: {} } };
  globalThis.window = { location, history, localStorage: storage, sessionStorage, innerWidth: 390, innerHeight: 844,
    addEventListener(type, listener) { if (!listeners.has(type)) listeners.set(type, new Set()); listeners.get(type).add(listener); },
    removeEventListener(type, listener) { listeners.get(type)?.delete(listener); },
    dispatchEvent() {}, setTimeout: timeout,
    clearTimeout(handle) { timeouts.delete(handle); clearTimeout(handle); },
    setInterval(fn, delay) { const handle = setInterval(fn, delay); handle.unref(); timers.add(handle); intervals.set(handle, { fn, delay }); return handle; },
    clearInterval(handle) { intervals.delete(handle); clearInterval(handle); },
    scrollTo() {}, matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
  };
  return { storage, values,
    async fireIntervals(delay) { await act(async () => { for (const timer of [...intervals.values()]) if (timer.delay === delay) timer.fn(); }); await settle(); },
    async fireWindow(type) { await act(async () => { for (const listener of [...(listeners.get(type) || [])]) listener(); }); await settle(); },
    async fireTimeouts(delay) {
      await act(async () => { for (const [handle, timer] of [...timeouts]) if (timer.delay === delay) {
        clearTimeout(handle); timeouts.delete(handle); await timer.fn();
      } });
      await settle();
    },
    cleanup() { for (const handle of timers) { clearTimeout(handle); clearInterval(handle); } },
  };
}
function fakeApi({ delayedGet = null, delayedCreate = null, delayedCatalog = null, completed = false, denyBind = false, patchFailure = null, catalogProjects = [project], storedSessions = [], positions = [] } = {}) {
  let created = 0;
  let patchFailuresRemaining = patchFailure ? 1 : 0;
  const sessions = new Map([['anonymous-draft', session('anonymous-draft')], ['account-a', session('account-a')], ['completed', session('completed', 'submitted')]]);
  for (const stored of storedSessions) sessions.set(stored.id, stored);
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    const pathname = String(url).split('?')[0];
    calls.push({ path: pathname, method: options.method || 'GET', headers: options.headers || {} });
    if (pathname === '/api/v1/projects') {
      if (delayedCatalog) await delayedCatalog.promise;
      return response({ items: catalogProjects });
    }
    if (pathname === '/api/v1/addons') return response([]);
    if (pathname.endsWith('/page-content')) return response({ store_id: 1, page_key: 'diy-home', title: '', subtitle: '', promo_banners: [], tea_options: [], coupon_prompt: {}, brand_story: {}, published: true });
    if (pathname === '/api/v1/coupons/templates') return response({ items: [] });
    if (pathname.endsWith('/service-position-map')) return response({ store_id: 1, positions });
    if (pathname === '/api/v1/auth/h5/me') {
      const token = options.headers.Authorization.split(' ')[1];
      return response(auth(JSON.parse(Buffer.from(token.split('.')[1], 'base64url')).sub).user);
    }
    if (pathname === '/api/v1/selection-sessions' && options.method === 'POST') {
      const id = 'new-' + ++created;
      const fresh = { ...session(id), items: [] };
      sessions.set(id, fresh);
      if (delayedCreate && created === 1) await delayedCreate.promise;
      return response({ session: fresh, access_token: id + '-owner' });
    }
    if (pathname.endsWith('/bind-customer')) return denyBind
      ? { ok: false, status: 409, json: async () => ({ detail: 'Synthetic ownership conflict' }) }
      : response({ selection_session_id: pathname.split('/')[4], customer_id: 42 });
    if (pathname.endsWith('/service-status')) return response({ selection_session_id: pathname.split('/')[4], occupancy_status: completed ? 'released' : null, service_ended_at: completed ? '2026-10-17T00:30:00Z' : null, can_evaluate: completed, evaluated: false });
    if (pathname === '/api/v1/selection-sessions/mine') {
      return response({ items: [session('anonymous-draft', 'submitted')], total: 1 });
    }
    if (pathname.startsWith('/api/v1/selection-sessions/')) {
      const id = pathname.split('/')[4];
      if (patchFailure && options.method === 'PATCH' && patchFailuresRemaining > 0) {
        patchFailuresRemaining -= 1;
        return { ok: false, status: 409, json: async () => ({ detail: patchFailure }) };
      }
      if (delayedGet && id === delayedGet.id && delayedGet.enabled) {
        delayedGet.enabled = false;
        await delayedGet.wait.promise;
      }
      return response(sessions.get(id));
    }
    if (pathname === '/api/v1/tracking/events') return response({});
    throw new Error('Unexpected synthetic request: ' + pathname);
  };
  return { calls, created: () => created, completeService() { completed = true; }, updateSession(value) { sessions.set(value.id, value); } };
}
const profile = app => app.root.find(node => typeof node.type === 'function' && node.type.name === 'ProfilePage');
const loginProps = app => app.root.find(node => typeof node.type === 'function' && node.type.name === 'RecordLoginDialog').props;
async function mount() {
  let app;
  await act(async () => { app = create(React.createElement(App), { createNodeMock: () => ({ scrollTo() {}, scrollIntoView() {}, focus() {}, addEventListener() {}, removeEventListener() {}, querySelectorAll: () => [], getBoundingClientRect: () => ({ width: 390, height: 844 }) }) }); });
  await settle();
  return app;
}
async function unmount(app) { await act(async () => app.unmount()); }

for (const page of ['', '&page=seats']) {
  test('login outside the menu preserves and claims the anonymous configured draft: ' + (page || 'hub'), async () => {
    const values = new Map([[privateKey, JSON.stringify(record())]]);
    let env = environment('http://synthetic.invalid/?store=1&view=menu' + page, values);
    const api = fakeApi();
    let app = await mount();
    await act(async () => profile(app).props.onAuthChange(auth(42)));
    await settle();
    assert.equal(JSON.parse(values.get(privateKey)).customerId, 42, 'verified login must claim the original draft on every entry');
    await unmount(app);
    env.cleanup();
    env = environment('http://synthetic.invalid/?store=1&view=menu&page=projects', values);
    app = await mount();
    assert.equal(loginProps(app).selectionSessionId, 'anonymous-draft');
    assert.equal(loginProps(app).selectionToken, 'anonymous-draft-owner');
    assert.equal(api.created(), 0, 'opening the menu must not silently create a replacement cart');
    assert.deepEqual(JSON.parse(values.get(privateKey)).items, selectedItems);
    await unmount(app);
    env.cleanup();
  });
}

test('a delayed old-account refresh cannot replace the new account session or token', async () => {
  const wait = deferred();
  const delayedGet = { id: 'account-a', enabled: false, wait };
  const env = environment('http://synthetic.invalid/?store=1&view=menu&page=projects', new Map([[privateKey, JSON.stringify(record('account-a', 41))], [authKey, JSON.stringify(auth(41))]]));
  fakeApi({ delayedGet });
  const app = await mount();
  assert.equal(loginProps(app).selectionSessionId, 'account-a');
  delayedGet.enabled = true;
  await act(async () => profile(app).props.onAuthChange(auth(41)));
  await settle();
  assert.equal(delayedGet.enabled, false, 'the original owner refresh must already be in flight');
  await act(async () => profile(app).props.onAuthChange(auth(42)));
  await settle();
  assert.equal(loginProps(app).selectionSessionId, 'new-1');
  await act(async () => wait.resolve());
  await settle();
  assert.equal(loginProps(app).selectionSessionId, 'new-1', 'late account A response must be ignored');
  assert.equal(loginProps(app).selectionToken, 'new-1-owner');
  assert.equal(JSON.parse(env.values.get(privateKey)).customerId, 42);
  await unmount(app);
  env.cleanup();
});

test('menu reload after a completed service starts an empty new private selection', async () => {
  const env = environment('http://synthetic.invalid/?store=1&view=menu&page=projects', new Map([[privateKey, JSON.stringify(record('completed'))]]));
  const api = fakeApi({ completed: true });
  const app = await mount();
  assert.equal(api.created(), 1, 'completed service must not permanently lock the menu to the old submitted selection');
  assert.equal(loginProps(app).selectionSessionId, 'new-1');
  assert.equal(JSON.parse(env.values.get(privateKey)).sessionId, 'new-1');
  await unmount(app);
  env.cleanup();
});

test('a late initialization response cannot replace a newer customer selection', async () => {
  const wait = deferred();
  const env = environment('http://synthetic.invalid/?store=1&view=menu&page=projects', new Map([[privateKey, JSON.stringify(record('account-a', 41))], [authKey, JSON.stringify(auth(41))]]));
  const api = fakeApi({ delayedCreate: wait });
  const app = await mount();
  const changeAuth = profile(app).props.onAuthChange;
  await act(async () => changeAuth(auth(42)));
  await settle();
  assert.equal(api.created(), 1);
  await act(async () => changeAuth(auth(43)));
  await settle();
  assert.equal(loginProps(app).selectionSessionId, 'new-2');
  await act(async () => wait.resolve());
  await settle();
  assert.equal(loginProps(app).selectionSessionId, 'new-2');
  assert.equal(loginProps(app).selectionToken, 'new-2-owner');
  assert.equal(JSON.parse(env.values.get(privateKey)).customerId, 43);
  await unmount(app);
  env.cleanup();
});

test('logout from the service hub cannot expose the previous named customer draft', async () => {
  const values = new Map([[privateKey, JSON.stringify(record('account-a', 41))], [authKey, JSON.stringify(auth(41))]]);
  let env = environment('http://synthetic.invalid/?store=1&view=menu', values);
  fakeApi();
  let app = await mount();
  await act(async () => profile(app).props.onAuthChange(null));
  await settle();
  assert.equal(values.has(privateKey), false);
  await unmount(app);
  env.cleanup();
  env = environment('http://synthetic.invalid/?store=1&view=menu&page=projects', values);
  app = await mount();
  assert.equal(loginProps(app).selectionSessionId, 'new-1');
  assert.equal(JSON.parse(values.get(privateKey)).customerId, null);
  await unmount(app);
  env.cleanup();
});

test('returning from a just-completed service opens a new editable private selection', async () => {
  const env = environment('http://synthetic.invalid/?store=1&view=menu&page=projects', new Map([[privateKey, JSON.stringify(record('completed'))]]));
  const api = fakeApi();
  const app = await mount();
  assert.equal(api.created(), 0);
  api.completeService();
  await env.fireIntervals(20000);
  const button = app.root.findAllByType('button').find(node => node.children.includes('返回项目列表'));
  await act(async () => button.props.onClick());
  await settle();
  assert.equal(api.created(), 1);
  assert.equal(loginProps(app).selectionSessionId, 'new-1');
  assert.equal(JSON.parse(env.values.get(privateKey)).sessionId, 'new-1');
  await unmount(app);
  env.cleanup();
});

test('failed anonymous ownership verification preserves the draft and never silently replaces it', async () => {
  const values = new Map([[privateKey, JSON.stringify(record())], [authKey, JSON.stringify(auth(42))]]);
  const env = environment('http://synthetic.invalid/?store=1&view=menu&page=projects', values);
  const api = fakeApi({ denyBind: true });
  const app = await mount();
  assert.equal(api.created(), 0);
  assert.equal(JSON.parse(values.get(privateKey)).customerId, null);
  assert.equal(JSON.parse(values.get(privateKey)).sessionId, 'anonymous-draft');
  assert.ok(JSON.stringify(app.toJSON()).includes('Synthetic ownership conflict'));
  await unmount(app);
  env.cleanup();
});

for (const mode of ['fresh', 'legacy-wire', 'same-wire-repair']) test('configured private draft reload preserves linked pricing: ' + mode, async () => {
  const choice = (id, type, linked = null) => ({ id, code: 'synthetic-' + id, name: 'Synthetic ' + id, description: '', choice_type: type,
    linked_project_id: linked, linked_project_code: linked ? 'hxy-head-30' : null, linked_catalog_version_id: null,
    charge_mode: linked ? 'inherit_linked_price' : 'free', independently_visible: false, coupon_eligible: false,
    annual_gift_eligible: false, qualifies_for_foot_bath_bundle: false, display_order: id, status: 'active', prices: [] });
  const base = { ...project, code: 'hxy-spa-60', category: 'care', catalog_version_id: 2,
    prices: [{ price_type: 'store', amount_cents: 9900 }, { price_type: 'member', amount_cents: 7900 }],
    option_groups: [{ id: 3, code: 'synthetic-options', name: 'Synthetic options', description: '', selection_mode: 'multiple',
      required: false, min_select: 0, max_select: 2, display_order: 1, choices: [choice(3, 'preference'), choice(5, 'linked_project', 2)] }] };
  const linked = { ...project, id: 2, code: 'hxy-head-30', name: 'Synthetic linked extra', category: 'small',
    prices: [{ price_type: 'store', amount_cents: 1200 }, { price_type: 'member', amount_cents: 1200 }] };
  const wireItems = [{ ...selectedItems[0], diy_preferences: [], catalog_version_id: 2, option_choice_ids: [3, 5] }];
  const incompleteDraft = { selectedProjectIds: [1], independentProjectIds: [1], projectLinkedIds: { 1: [] },
    projectPreferences: { 1: [] }, projectAddonIds: { 1: [] }, localParts: [], tea: null,
    projectCatalogSelections: { 1: { projectId: 1, catalogVersionId: 2, optionChoiceIds: [3, 5] } } };
  const values = new Map([[privateKey, JSON.stringify({ ...record(), items: mode === 'fresh' ? [] : wireItems,
    ...(mode === 'same-wire-repair' ? { draft: incompleteDraft } : {}) })]]);
  let env = environment('http://synthetic.invalid/?store=1&view=menu&page=projects', values);
  const api = fakeApi({ catalogProjects: [base, linked] });
  let app = await mount();
  const total = () => app.root.findByProps({ className: 'selection-summary-total' }).findByType('strong').children.join('');
  if (mode === 'legacy-wire') assert.equal(total(), '¥111', 'legacy wire items must restore verified linked metadata');
  if (mode === 'same-wire-repair') assert.equal(total(), '¥99');
  const selectBase = app.root.findByProps({ 'aria-label': (mode === 'fresh' ? '选择' : '调整') + 'Synthetic project' });
  await act(async () => selectBase.props.onClick({ stopPropagation() {} }));
  const detail = app.root.find(node => typeof node.type === 'function' && node.type.name === 'ProjectDetailPage');
  await act(async () => detail.props.onConfirm({ project: base, preferences: [], addonIds: [], localParts: [],
    catalogVersionId: 2, optionChoiceIds: [3, 5], linkedProjectIds: [2] }));
  await settle();
  assert.equal(total(), '¥111');
  const before = JSON.parse(values.get(privateKey));
  assert.deepEqual(before.items[0].option_choice_ids, [3, 5]);
  assert.deepEqual(before.draft.projectLinkedIds, { 1: [2] }, 'unchanged wire items must still persist repaired local references');
  assert.equal(before.items[0].catalog_selection, undefined, 'wire items intentionally omit server linked snapshots');
  await unmount(app);
  env.cleanup();
  env = environment('http://synthetic.invalid/?store=1&view=menu&page=projects', values);
  app = await mount();
  assert.equal(total(), '¥111', 'reload must not drop the selected linked project from the menu total');
  assert.equal(loginProps(app).selectionSessionId, before.sessionId);
  assert.equal(loginProps(app).selectionToken, before.accessToken);
  assert.equal(api.created(), 0, 'restoring configuration must not replace the original session');
  await act(async () => app.root.findByProps({ 'aria-label': '调整Synthetic project' }).props.onClick({ stopPropagation() {} }));
  const restoredDetail = app.root.find(node => typeof node.type === 'function' && node.type.name === 'ProjectDetailPage');
  assert.deepEqual(restoredDetail.props.linkedProjectIds, [2]);
  assert.deepEqual(restoredDetail.props.catalogSelection.optionChoiceIds, [3, 5]);
  await unmount(app);
  env.cleanup();
});

test('shared seat polling and submission lock cannot overwrite a separate private draft or accept its late response', { timeout: 5000 }, async (t) => {
  const privateDraft = JSON.stringify(record());
  const values = new Map([[privateKey, privateDraft]]);
  const wait = deferred();
  const delayedGet = { id: 'anonymous-draft', enabled: true, wait };
  let env = environment('http://synthetic.invalid/?store=1&view=menu&page=projects', values);
  fakeApi({ delayedGet });
  const oldApp = await mount();
  assert.equal(delayedGet.enabled, false, 'the private read must be in flight before leaving its page');
  await unmount(oldApp);
  env.cleanup();

  const sharedProject = { ...project, id: 2, code: 'hxy-head-30', category: 'small', name: 'Synthetic shared project',
    prices: [{ price_type: 'store', amount_cents: 1200 }, { price_type: 'member', amount_cents: 1200 }] };
  const shared = { ...session('shared-draft'), items: [{ ...selectedItems[0], project_id: 2, diy_preferences: [] }],
    store_total_cents: 1200, member_total_cents: 1200, cart_version: 1 };
  const occupancy = { id: 1, store_id: 1, room_id: 1, active_room_id: 1, selection_session_id: shared.id,
    status: 'held', source: 'store_qr', version: 1, hold_expires_at: null };
  const position = { id: 1, code: 'synthetic-sofa', name: 'Synthetic sofa', customer_label: 'Synthetic sofa',
    type: 'sofa', state: 'held', is_current: true, customer_selectable: true, operational_status: 'active', occupancy };
  values.set('hxy_diy_entry_1_synthetic-sofa', JSON.stringify({ storeId: 1, positionCode: position.code,
    accessToken: '', collaborationToken: 'synthetic-collaborator', collaborationMode: 'shared_draft',
    visitFeedbackToken: 'synthetic-feedback', cartVersion: 1, session: shared, occupancy, position }));
  env = environment('http://synthetic.invalid/?store=1&seat=synthetic-sofa&source=store_qr', values);
  const api = fakeApi({ catalogProjects: [project, sharedProject], storedSessions: [shared], positions: [position] });
  const app = await mount();
  t.after(async () => { await unmount(app); env.cleanup(); });
  const total = () => app.root.findByProps({ className: 'selection-summary-total' }).findByType('strong').children.join('');
  assert.equal(loginProps(app).selectionSessionId, shared.id);
  assert.equal(total(), '¥12');
  assert.equal(values.get(privateKey), privateDraft, 'entering a shared seat must not transfer or replace the private draft');
  await act(async () => app.root.findByProps({ className: 'selection-summary' }).props.onClick());
  await act(async () => app.root.findByProps({ 'aria-label': '增加Synthetic shared project' }).props.onClick());
  await env.fireTimeouts(500);
  const sharedWrites = api.calls.filter(call => call.method === 'PATCH');
  assert.ok(sharedWrites.length > 0, 'the real shared autosave branch must run before lock');
  assert.ok(sharedWrites.every(call => call.path.endsWith('/shared-draft') && call.headers['X-Collaboration-Token'] === 'synthetic-collaborator' && !call.headers['X-Selection-Token']));

  const updated = { ...shared, cart_version: 2, items: [{ ...shared.items[0], quantity: 3 }], store_total_cents: 3600, member_total_cents: 3600 };
  api.updateSession(updated);
  await env.fireWindow('focus');
  assert.equal(total(), '¥36', 'a newer shared version must update the shared UI');
  await act(async () => wait.resolve());
  await settle();
  assert.equal(loginProps(app).selectionSessionId, shared.id, 'late private initialization must not replace the shared session');
  assert.equal(total(), '¥36');
  assert.equal(values.get(privateKey), privateDraft);
  assert.equal(api.created(), 0, 'shared entry must not create a new private selection');

  const writesBeforeLock = api.calls.filter(call => call.method === 'PATCH').length;
  api.updateSession({ ...updated, status: 'submitted', submitted_at: '2026-10-17T00:00:00Z' });
  await env.fireWindow('focus');
  assert.ok(JSON.stringify(app.toJSON()).includes('本服务位清单已提交；可继续浏览项目或提交评价与建议'));
  await act(async () => app.root.findByProps({ 'aria-label': '选择Synthetic shared project' }).props.onClick({ stopPropagation() {} }));
  const detail = app.root.find(node => typeof node.type === 'function' && node.type.name === 'ProjectDetailPage');
  assert.equal(detail.props.readOnly, true, 'submitted collaborator detail must be read-only');
  await env.fireTimeouts(500);
  assert.equal(api.calls.filter(call => call.method === 'PATCH').length, writesBeforeLock, 'a queued autosave must be cancelled after lock');
  assert.equal(api.calls.filter(call => call.method === 'POST' && call.path.endsWith('/revisions')).length, 0);
  assert.equal(values.get(privateKey), privateDraft);
});

test('menu draft 409 recreates a private draft instead of showing the seat-released page', async () => {
  const env = environment(
    'http://synthetic.invalid/?store=1&view=menu&page=projects',
    new Map([[privateKey, JSON.stringify({ ...record(), items: [] })]]),
  );
  const api = fakeApi({ patchFailure: { code: 'CURRENT_VERSION_CONFLICT', message: '选单已更新' } });
  const app = await mount();
  assert.equal(loginProps(app).selectionSessionId, 'anonymous-draft');
  await act(async () => app.root.findByProps({ 'aria-label': '选择Synthetic project' }).props.onClick({ stopPropagation() {} }));
  const detail = app.root.find(node => typeof node.type === 'function' && node.type.name === 'ProjectDetailPage');
  await act(async () => detail.props.onConfirm({ project: detail.props.project, preferences: [], addonIds: [], localParts: [] }));
  await env.fireTimeouts(500);
  assert.equal(api.created(), 1, 'public menu must create a replacement private draft');
  assert.equal(loginProps(app).selectionSessionId, 'new-1');
  assert.equal(JSON.parse(env.values.get(privateKey)).sessionId, 'new-1');
  assert.equal(JSON.stringify(app.toJSON()).includes('本次位置已释放'), false);
  await unmount(app);
  env.cleanup();
});

test('my page opens service history on demand after login on the seat-free menu', async () => {
  const env = environment(
    'http://synthetic.invalid/?store=1&view=menu&page=projects',
    new Map([[privateKey, JSON.stringify(record())]]),
  );
  fakeApi();
  const app = await mount();
  await act(async () => profile(app).props.onAuthChange(auth(42)));
  await settle();
  await act(async () => app.root.findByProps({ className: 'miniapp-profile-entry' }).props.onClick());
  await settle();
  assert.equal(app.root.findAllByProps({ id: 'profile-records' }).length, 0, 'history must stay collapsed initially');
  const historyButton = app.root.find(node => node.type === 'button' && node.props['aria-controls'] === 'profile-records' && !node.props['aria-label']);
  await act(async () => historyButton.props.onClick({ currentTarget: { focus() {} } }));
  assert.equal(app.root.findAllByProps({ id: 'profile-records' }).length, 1, 'history shortcut must expose the service list');
  const text = JSON.stringify(app.toJSON());
  assert.ok(text.includes('待前台确认') || text.includes('Synthetic project'), 'submitted selection must be listed');
  await unmount(app);
  env.cleanup();
});

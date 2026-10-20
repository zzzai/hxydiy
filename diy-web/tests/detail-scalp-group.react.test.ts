import assert from 'node:assert/strict';
import test, { before, after } from 'node:test';
import { createRequire } from 'node:module';
import { createServer } from 'vite';

const require = createRequire(import.meta.url);
const React = require('react');
const { create, act } = require('react-test-renderer');
let server: Awaited<ReturnType<typeof createServer>>;
let ProjectDetailPage: any;

before(async () => {
  server = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
  ProjectDetailPage = (await server.ssrLoadModule('/src/components/ProjectDetailPage.tsx')).default;
});
after(async () => { await server?.close(); });

function project(id: number, code: string, name: string, category: string, store: number, member: number) {
  return { id, code, name, category, category_mark: '', duration_min: 30, summary: '',
    image_url: '', tags: [], price_label: '', prices: [
      { price_type: 'store', amount_cents: store }, { price_type: 'member', amount_cents: member },
    ] };
}
function choice(id: number, linked: number | null, name: string, bodyPart: string | null = null) {
  return { id, code: `synthetic-${id}`, name, description: '', choice_type: linked ? 'linked_project' : 'preference',
    linked_project_id: linked, linked_project_code: linked === 3 ? 'hxy-head-30' : null,
    linked_catalog_version_id: null, charge_mode: linked ? 'inherit_linked_price' : 'free',
    independently_visible: false, coupon_eligible: false, annual_gift_eligible: false,
    qualifies_for_foot_bath_bundle: bodyPart !== null, display_order: id, status: 'active', prices: [],
    body_part: bodyPart };
}
function group(id: number, choices: any[], required = false) {
  return { id, code: `group-${id}`, name: required ? '手法力度' : '加购', description: '',
    selection_mode: required ? 'single' : 'multiple', required, min_select: required ? 1 : 0,
    max_select: required ? 1 : 10, display_order: id, choices };
}
function text(node: any): string {
  return typeof node === 'string' ? node : (node.children || []).map(text).join('');
}
function buttons(node: any, name: string) {
  return node.findAll((item: any) => item.type === 'button'
    && item.findAll((child: any) => child.type === 'strong' && text(child) === name).length > 0);
}
function section(app: any, name: string) {
  return app.root.findAll((node: any) => node.type === 'section'
    && node.findAll((item: any) => item.type === 'div' && item.props.className === 'mini-config-title'
      && item.findAll((title: any) => title.type === 'strong' && text(title) === name).length > 0).length > 0);
}

async function mount({ code = 'hxy-qiqing-30', catalog = true, linkedHead = true,
  local = true, other = true, member = false, readOnly = false, selectedHead = false } = {}) {
  const originals = ['document', 'window'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)] as const);
  Object.defineProperty(globalThis, 'document', { configurable: true, value: { body: { style: {} } } });
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { addEventListener() {}, removeEventListener() {} } });
  const main: any = project(1, code, '现煮草本泡', 'footbath', 1990, 1990);
  if (catalog) Object.assign(main, { catalog_version_id: 10, option_groups: [
    group(1, [choice(101, null, '适中')], true),
    group(2, [...(local ? [choice(201, 2, '肩颈', '肩颈'), choice(202, 2, '腰臀', '腰臀')] : []),
      ...(linkedHead ? [choice(301, 3, '头疗')] : []), ...(other ? [choice(302, 4, '采耳')] : [])]),
  ] });
  const projects = [main, ...(local ? [project(2, 'hxy-jubu-30', '局部推拿', 'local-strength', 7900, 4900)] : []),
    project(3, 'hxy-head-30', '头疗', 'small', 7900, 4900),
    ...(other ? [project(4, 'hxy-caier-30', '采耳', 'small', 8900, 5900)] : [])];
  const addons = [{ id: 7, code: 'hxy-addon-head', name: '头部放松', parent_project_id: null,
    duration_min: 15, summary: '', image_url: '', display_order: 0, chargeable: true,
    independently_sellable: false, can_attach_to_parent: true, prices: { store: 2900, member: 2900 } }];
  let payload: any;
  let app: any;
  const props = { project: main, projects, addons, selectedProjectIds: [], selectedAddonIds: [], preferences: [],
    localParts: [], catalogSelection: catalog ? { catalogVersionId: 10, optionChoiceIds: [101, ...(selectedHead && linkedHead ? [301] : [])] } : undefined,
    linkedProjectIds: selectedHead && !linkedHead ? [3] : [], coupon: null, positionLabel: '测试服务位',
    isMember: member, readOnly, onClose() {}, onShare() {}, onCouponInfo() {}, onConfirm(value: any) { payload = value; } };
  try {
    await act(async () => { app = create(React.createElement(ProjectDetailPage, props)); });
  } catch (error) {
    restore();
    throw error;
  }
  function restore() {
    for (const [key, descriptor] of originals) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else delete (globalThis as any)[key];
    }
  }
  return {
    app,
    async click(name: string) { await act(async () => buttons(app.root, name)[0].props.onClick()); },
    total() { return text(app.root.findByProps({ className: 'mini-detail-total' }).findByType('strong')); },
    progress() { return text(app.root.findByProps({ role: 'status' })); },
    async confirm() {
      await act(async () => app.root.findByProps({ className: 'mini-detail-actions' }).findByType('button').props.onClick());
      return payload;
    },
    async close() { await act(async () => app.unmount()); restore(); },
  };
}

for (const linkedHead of [true, false]) {
  for (const member of [false, true]) {
    test(`head care moves once and retains ${linkedHead ? 'choice' : 'direct project'} selection and ${member ? 'member' : 'store'} pricing`, async () => {
      const subject = await mount({ linkedHead, member });
      try {
        const upper = section(subject.app, '重点多按一会');
        const lower = section(subject.app, '再放松一会');
        assert.equal(upper.length, 1);
        assert.equal(buttons(upper[0], '头疗').length, 1);
        assert.equal(buttons(lower[0], '头疗').length, 0);
        assert.equal(buttons(subject.app.root, '头疗').length, 1);
        assert.match(text(buttons(upper[0], '头疗')[0]), /约30分钟/);
        assert.equal(subject.total(), '¥19.9');
        await subject.click('头疗');
        assert.equal(buttons(upper[0], '头疗')[0].props['aria-pressed'], true);
        assert.equal(subject.total(), member ? '¥68.9' : '¥98.9');
        assert.match(subject.progress(), /0\/2/);
        const chosen = await subject.confirm();
        assert.deepEqual(chosen.localParts, []);
        assert.deepEqual(chosen.addonIds, []);
        assert.deepEqual(chosen.optionChoiceIds, linkedHead ? [101, 301] : [101]);
        assert.deepEqual(chosen.linkedProjectIds, [3]);
        assert.equal(chosen.catalogVersionId, 10);
        await subject.click('肩颈调理');
        assert.match(subject.progress(), /1\/2/);
        assert.equal(subject.total(), member ? '¥117.9' : '¥177.9');
        await subject.click('腰臀调理');
        assert.match(subject.progress(), /已免基础泡脚费/);
        assert.equal(subject.total(), member ? '¥147' : '¥237');
        await subject.click('头疗');
        assert.equal(buttons(upper[0], '头疗')[0].props['aria-pressed'], false);
        assert.equal(subject.total(), member ? '¥98' : '¥158');
        const cleared = await subject.confirm();
        assert.deepEqual(cleared.localParts, ['肩颈', '腰臀']);
        assert.deepEqual(cleared.optionChoiceIds, [101, 201, 202]);
        assert.deepEqual(cleared.linkedProjectIds, [2]);
      } finally { await subject.close(); }
    });
  }
}

test('head-only catalog renders the upper group without an empty lower group', async () => {
  const subject = await mount({ local: false, other: false });
  try {
    assert.equal(section(subject.app, '重点多按一会').length, 1);
    assert.equal(buttons(section(subject.app, '重点多按一会')[0], '头疗').length, 1);
    assert.equal(section(subject.app, '再放松一会').length, 0);
    await subject.click('头疗');
    assert.deepEqual((await subject.confirm()).localParts, []);
    assert.match(subject.progress(), /0\/2/);
  } finally { await subject.close(); }
});

for (const code of ['hxy-xiangxiang-60', 'hxy-xiaoqi-90', 'hxy-tuina-70', 'hxy-spa-60', 'hxy-spa-90']) {
  test(`other project ${code} retains head care in the lower group`, async () => {
    const subject = await mount({ code });
    try {
      assert.equal(buttons(section(subject.app, '再放松一会')[0], '头疗').length, 1);
      for (const upper of section(subject.app, '重点多按一会')) assert.equal(buttons(upper, '头疗').length, 0);
      await subject.click('头疗');
      const payload = await subject.confirm();
      assert.deepEqual(payload.optionChoiceIds, [101, 301]);
      assert.deepEqual(payload.localParts, []);
      assert.deepEqual(payload.linkedProjectIds, [3]);
    } finally { await subject.close(); }
  });
}

test('legacy head relaxation remains its distinct addon and is not replaced with head care', async () => {
  const subject = await mount({ catalog: false });
  try {
    assert.equal(buttons(subject.app.root, '头疗').length, 0);
    assert.equal(buttons(section(subject.app, '再放松一会')[0], '头部放松').length, 1);
    await subject.click('头部放松');
    assert.equal(subject.total(), '¥48.9');
    assert.match(subject.progress(), /0\/2/);
    const selected = await subject.confirm();
    assert.deepEqual(selected.addonIds, [7]);
    assert.deepEqual(selected.localParts, []);
    assert.equal(selected.optionChoiceIds, undefined);
    await subject.click('头部放松');
    assert.deepEqual((await subject.confirm()).addonIds, []);
  } finally { await subject.close(); }
});

for (const linkedHead of [true, false]) {
  test(`restored ${linkedHead ? 'choice' : 'direct project'} head selection stays selected and read-only`, async () => {
    const subject = await mount({ linkedHead, selectedHead: true, readOnly: true });
    try {
      const headButtons = buttons(section(subject.app, '重点多按一会')[0], '头疗');
      assert.equal(headButtons.length, 1);
      const button = headButtons[0];
      assert.equal(button.props['aria-pressed'], true);
      assert.equal(button.props.disabled, true);
      await subject.click('头疗');
      assert.equal(subject.total(), '¥98.9');
      assert.equal(button.props['aria-pressed'], true);
      assert.match(subject.progress(), /0\/2/);
    } finally { await subject.close(); }
  });
}

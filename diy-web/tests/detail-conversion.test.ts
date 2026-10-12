import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer, type ViteDevServer } from 'vite';
import type { Project } from '../src/domain.ts';
import { projectDetailVisuals } from '../src/projectDetailVisuals.ts';

let server: ViteDevServer;
let ProjectDetailPage: typeof import('../src/components/ProjectDetailPage.tsx').default;
let LocalDetailPage: typeof import('../src/components/LocalDetailPage.tsx').default;

before(async () => {
  server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
  ProjectDetailPage = (await server.ssrLoadModule('/src/components/ProjectDetailPage.tsx')).default;
  LocalDetailPage = (await server.ssrLoadModule('/src/components/LocalDetailPage.tsx')).default;
});
after(async () => { await server?.close(); });

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: 1, code: 'hxy-qiqing-30', name: '现煮草本泡', category: 'footbath-diy', category_mark: '泡',
    duration_min: null, summary: '', image_url: '', tags: [], price_label: '',
    prices: [{ price_type: 'store', amount_cents: 2990 }, { price_type: 'member', amount_cents: 2590 }],
    ...overrides,
  };
}

const localProject = project({ id: 2, code: 'hxy-jubu-30', name: '局部推拿', category: 'local-strength',
  prices: [{ price_type: 'store', amount_cents: 7900 }, { price_type: 'member', amount_cents: 4900 }] });

function renderProject(item = project(), overrides: Record<string, unknown> = {}) {
  return renderToStaticMarkup(createElement(ProjectDetailPage, {
    project: item, projects: [item, localProject], addons: [], selectedProjectIds: [], selectedAddonIds: [],
    preferences: [], localParts: [], coupon: null, positionLabel: '', isMember: false,
    onClose: () => {}, onConfirm: () => {}, onCouponInfo: () => {}, onShare: () => {}, ...overrides,
  }));
}

function pressureGroup() {
  return { id: 10, code: 'pressure', name: '手法力度', description: '', selection_mode: 'single', required: true,
    min_select: 1, max_select: 1, display_order: 1, choices: [
      { id: 200, code: 'pressure-medium', name: '适中', description: '', choice_type: 'preference',
        linked_project_id: null, linked_project_code: null, linked_catalog_version_id: null,
        charge_mode: 'free', independently_visible: false, coupon_eligible: false, annual_gift_eligible: false,
        qualifies_for_foot_bath_bundle: false, display_order: 1, status: 'active', prices: [] },
    ] } as NonNullable<Project['option_groups']>[number];
}

test('basic footbath does not imply included massage in either catalog or fallback controls', () => {
  assert.doesNotMatch(renderProject(), /手法力度/);
  assert.doesNotMatch(renderProject(project({ catalog_version_id: 8, option_groups: [pressureGroup()] })), /手法力度/);
  assert.match(renderProject(project({ code: 'hxy-tuina-70', name: '荷小推', category: 'tuina', duration_min: 80 })), /手法力度/);
});

test('DIY preferences and additions are expanded before the service explanation', () => {
  const markup = renderProject();
  const experience = markup.indexOf('aria-label="项目体验介绍"');
  const preferences = markup.indexOf('aria-label="服务偏好"');
  const additions = markup.indexOf('aria-label="可选加购"');
  assert.ok(preferences >= 0 && additions > preferences && experience > additions);
  assert.ok(markup.indexOf('class="detail-selection-reason"') > additions);
  assert.match(markup, /<details[^>]*aria-label="服务偏好"[^>]*\sopen=""[^>]*>/);
  assert.match(markup, /<details[^>]*aria-label="可选加购"[^>]*\sopen=""[^>]*>/);
  assert.match(markup, /¥29\.9/);
  assert.match(markup, /会员价 ¥25\.9/);
});

test('existing additions stay discoverable without changing their price preview', () => {
  const markup = renderProject(project(), { localParts: ['肩颈'] });
  assert.match(markup, /<details[^>]*aria-label="可选加购"[^>]*\sopen=""[^>]*>/);
  assert.match(markup, /mini-detail-total[\s\S]*¥108\.9/);
});

test('invalid required choices expose preferences and keep confirmation blocked', () => {
  const item = project({ code: 'hxy-tuina-70', name: '荷小推', category: 'tuina', duration_min: 80,
    catalog_version_id: 8, option_groups: [pressureGroup()] });
  const markup = renderProject(item, { catalogSelection: { catalogVersionId: 8, optionChoiceIds: [999] } });
  assert.match(markup, /<details[^>]*aria-label="服务偏好"[^>]*\sopen=""[^>]*>/);
  assert.match(markup, /class="primary"[^>]*disabled=""/);
});

test('package per-session explanation derives from the real total and session count', () => {
  const kit = project({ code: 'hxy-taoke-60', name: '功夫调理', category: 'kit', duration_min: 60,
    price_label: '10次/套', prices: [{ price_type: 'member', amount_cents: 98000 }] });
  assert.match(renderProject(kit), /¥98\/次/);
  assert.match(renderProject(kit), /¥980/);
  assert.match(renderProject(kit), /无有效期/);
  assert.doesNotMatch(renderProject(kit), /未用不退/);
  assert.match(renderProject({ ...kit, price_label: '8次/套' }), /¥122\.5\/次/);
  assert.match(renderProject({ ...kit, prices: [{ price_type: 'member', amount_cents: 120000 }] }), /¥120\/次/);
  assert.doesNotMatch(renderProject({ ...kit, price_label: '' }), /¥98\/次/);
});

test('local-part presentation distinguishes zero selections and member-priced selected parts', () => {
  const renderLocal = (parts: string[], isMember: boolean) => renderToStaticMarkup(createElement(LocalDetailPage, {
    open: true, project: localProject, selectedParts: parts, positionLabel: '1号沙发', isMember,
    onClose: () => {}, onConfirm: () => {},
  }));
  const empty = renderLocal([], false);
  assert.match(empty, /id="local-detail-title">局部推拿<\/h1>/);
  assert.equal((empty.match(/aria-pressed="true"/g) || []).length, 0);
  assert.match(empty, /mini-detail-total[\s\S]*¥0/);
  assert.match(empty, /class="primary"[^>]*disabled=""/);
  const selected = renderLocal(['肩颈', '腰臀'], true);
  assert.equal((selected.match(/aria-pressed="true"/g) || []).length, 2);
  assert.match(selected, /mini-detail-total[\s\S]*¥98/);
});

test('experience cards never repeat their body as a heading or reuse one fallback body', () => {
  for (const code of ['hxy-xiangxiang-60', 'hxy-tuina-70', 'hxy-spa-90', 'hxy-head-30', 'hxy-caier-30', 'hxy-taoke-60']) {
    const sections = projectDetailVisuals(code);
    assert.ok(sections.every(section => section.title !== section.body), code);
    assert.equal(new Set(sections.map(section => section.body)).size, sections.length, code);
  }
});

test('back-oil detail uses its dedicated existing illustration rather than the SPA hero', () => {
  const markup = renderProject(project({ code: 'hxy-oil-back-30', name: '精油开背', category: 'small',
    image_url: '/assets/projects/hxy-spa-60.webp', duration_min: 30 }));
  assert.match(markup, /class="mini-detail-hero[^"\n]*" src="[^"]*hxy-oil-back-30-detail\.webp"/);
});

test('optional services never invent a duration when the published project has none', () => {
  const base = project({ catalog_version_id: 8, option_groups: [pressureGroup()] });
  const ear = project({ id: 3, code: 'hxy-caier-30', name: '采耳', category: 'small', duration_min: null });
  const markup = renderProject(base, { projects: [base, localProject, ear] });
  assert.doesNotMatch(markup, /约15分钟/);
  assert.match(markup, /时长向前台确认/);
});

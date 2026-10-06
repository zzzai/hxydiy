import test from 'node:test';
import assert from 'node:assert/strict';
import { additionalIncludedServices, hasProjectPrice, includedServiceLabel, serviceFacts, serviceUnitLabel, type ServiceSpec } from '../src/serviceSpec.ts';
import { buildSelectionItems, displayProjectName, isDetailOnlyProject, type Project } from '../src/domain.ts';
import { buildSelectionSummary, emptySelectionDraft } from '../src/selectionSummary.ts';

const spec: ServiceSpec = { version: 'menu-20261001', flow_steps: ['按摩'], sale_unit: 'service', services_per_unit: 1, service_duration_min: 60, included_services: [{ code: 'hxy-qiqing-30', name: '现煮草本泡', quantity: 1 }] };
const project = (id: number, code: string, service_spec?: ServiceSpec | null): Project => ({ id, code, name: code, category: 'care', category_mark: '补', duration_min: 60, summary: '旧说明', image_url: '', tags: [], price_label: '', prices: [{ price_type: 'store', amount_cents: 12900 }], service_spec });
const spa = project(41, 'hxy-spa-60', spec);
const bath = project(98, 'hxy-qiqing-30', null);
const kit = { ...project(6, 'hxy-taoke-60', { ...spec, sale_unit: 'package', services_per_unit: 10, included_services: [] }), category: 'kit', prices: [{ price_type: 'store', amount_cents: 98000 }] };

test('null contract preserves legacy names and empty service facts', () => {
  assert.equal(serviceFacts(null), '');
  assert.equal(serviceUnitLabel(undefined), '');
  assert.equal(displayProjectName({ ...spa, service_spec: null }), '60分钟精油SPA');
  assert.equal(displayProjectName({ ...spa, name: '舒压精油SPA' }), '舒压精油SPA');
});

test('included description does not create a paid gift or remove a separately selected service', () => {
  const items = buildSelectionItems({ projects: [spa, bath], selectedProjectIds: [41, 98], localParts: [], tea: null });
  assert.deepEqual(items.map(item => item.project_id), [41, 98]);
  assert.deepEqual(additionalIncludedServices(items, [spa, bath]).map(item => item.id), [98]);
  assert.deepEqual(additionalIncludedServices(items.slice(0, 1), [spa, bath]), []);
  assert.deepEqual(additionalIncludedServices(items, [{ ...spa, service_spec: null }, bath]), []);
  assert.equal(includedServiceLabel(spec), '已含1次现煮草本泡');
});

test('package remains detail-only and quantities/prices describe whole packages', () => {
  assert.equal(isDetailOnlyProject(kit), true);
  assert.equal(serviceUnitLabel(kit.service_spec), '10次/套 · 每次60分钟');
  const summary = buildSelectionSummary({ projects: [kit], addons: [], draft: { ...emptySelectionDraft(), selectedProjectIds: [6, 6] }, isMember: false });
  assert.equal(summary.groups[0].quantityUnit, '套');
  assert.equal(summary.groups[0].quantity, 2);
  assert.equal(summary.groups[0].priceCents, 196000);
  assert.equal(summary.groups[0].memberPriceCents, null);
});

test('unknown price is different from an explicitly free API price', () => {
  assert.equal(hasProjectPrice({ ...bath, prices: [] }), false);
  assert.equal(hasProjectPrice({ ...bath, prices: [{ price_type: 'store', amount_cents: 0 }] }), true);
  assert.equal(hasProjectPrice(kit, 'member'), false);
  const summary = buildSelectionSummary({ projects: [{ ...bath, prices: [] }], addons: [], draft: { ...emptySelectionDraft(), selectedProjectIds: [98] }, isMember: false });
  assert.equal(summary.groups[0].priceLabel, '价格待确认');
});

test('a frozen service specification is displayed independently of the live catalog', () => {
  const frozen = { ...spec, services_per_unit: 5, sale_unit: 'package' as const, service_duration_min: 45, included_services: [] };
  assert.equal(serviceFacts(frozen), '5次/套 · 每次45分钟');
  assert.equal(serviceFacts(kit.service_spec), '10次/套 · 每次60分钟');
});

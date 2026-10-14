import assert from 'node:assert/strict';
import test from 'node:test';
import * as draftApi from '../src/selectionSummary.ts';
import { buildSelectionItems } from '../src/domain.ts';
import * as flow from '../src/selectionFlow.ts';

const save = (draft: draftApi.SelectionDraft, id: number, links: number[] = []) => {
  assert.equal(typeof draftApi.saveProjectSelection, 'function');
  return draftApi.saveProjectSelection(draft, { projectId: id, preferences: [], addonIds: [], localParts: [], linkedProjectIds: links });
};

test('saving A or B detail preserves two independently selected units of A', () => {
  const draft = { ...draftApi.emptySelectionDraft(), selectedProjectIds: [1, 1] };
  assert.deepEqual(save(draft, 1).selectedProjectIds, [1, 1]);
  assert.deepEqual(save(draft, 2).selectedProjectIds, [1, 1, 2]);
});

test('cancelling one linked source preserves independent quantity and other sources', () => {
  let draft = save(draftApi.emptySelectionDraft(), 1, [3]);
  draft = save(draft, 2, [3]);
  draft = save(draft, 1);
  assert.equal(draft.selectedProjectIds.filter(id => id === 3).length, 1);
  draft = save(draft, 2);
  assert.equal(draft.selectedProjectIds.includes(3), false);
  const independent = { ...draftApi.emptySelectionDraft(), selectedProjectIds: [3, 3] };
  assert.equal(save(save(independent, 1, [3]), 1).selectedProjectIds.filter(id => id === 3).length, 2);
});

test('removing a parent removes only its linked contribution', () => {
  const linked = save(save(draftApi.emptySelectionDraft(), 1, [3]), 2, [3]);
  const removed = draftApi.removeSelectionEntry(linked, { kind: 'project', projectId: 1 });
  assert.deepEqual(removed.selectedProjectIds, [2, 3]);
  assert.equal(draftApi.removeSelectionEntry(removed, { kind: 'project', projectId: 2 }).selectedProjectIds.includes(3), false);
});

test('submitted and confirmed revisions carry original snapshot plus only new draft quantities', () => {
  assert.equal(typeof flow.revisionItems, 'function');
  const base = [{ project_id: 1, quantity: 2, addon_ids: [], diy_preferences: [], item_type: 'service' as const, chargeable: true }];
  const added = [{ ...base[0], quantity: 1 }];
  for (const status of ['submitted', 'confirmed'] as const) assert.equal(flow.revisionItems(status, base, added)[0].quantity, 3);
  assert.equal(flow.revisionItems('draft', base, added)[0].quantity, 1);
});

test('full revision inputs do not echo derived catalog units as independent purchase lines', () => {
  const parent = { project_id: 1, quantity: 1, addon_ids: [], diy_preferences: [], item_type: 'service' as const, chargeable: true, catalog_version_id: 10, option_choice_ids: [101] };
  const linked = { ...parent, project_id: 3, item_kind: 'catalog_linked_project', source_project_id: 1 };
  const result = flow.revisionItems('confirmed', [parent, linked], [{ ...parent, quantity: 1 }]);
  assert.deepEqual(result.map(item => [item.project_id, item.quantity]), [[1, 2]]);
});

test('post-submit selection calls use owner credential, never the frozen collaborator token', () => {
  assert.equal(typeof flow.selectionRequestAccess, 'function');
  assert.deepEqual(flow.selectionRequestAccess('draft', 'owner', 'collaborator', 8, 'auth'), { collaborationToken: 'collaborator', expectedVersion: 8, authToken: 'auth' });
  assert.deepEqual(flow.selectionRequestAccess('submitted', 'owner', 'collaborator', 9, 'auth'), { authToken: 'auth' });
  assert.equal(flow.selectionRequestAccess('submitted', '', 'collaborator', 9), null);
});

test('submit drops owner collaboration access but keeps a companion browse-only credential for safe restore', () => {
  assert.equal(typeof flow.submittedSelectionAccess, 'function');
  assert.deepEqual(flow.submittedSelectionAccess('owner', 'collaborator'), { collaborationToken: '', collaborationMode: '' });
  assert.deepEqual(flow.submittedSelectionAccess('', 'collaborator'), { collaborationToken: 'collaborator', collaborationMode: 'browse_only' });
});

test('quantity plus retains the independent source and can add a second unit', () => {
  const draft = save(draftApi.emptySelectionDraft(), 1, [3]);
  const increased = draftApi.changeSelectionQuantity(draft, { kind: 'project', projectId: 1 }, 1);
  assert.equal(increased.selectedProjectIds.filter(id => id === 1).length, 2);
  assert.equal(save(increased, 1, [3]).selectedProjectIds.filter(id => id === 1).length, 2);
});

test('hydration preserves server catalog provenance and independent quantities', () => {
  assert.equal(typeof draftApi.hydrateSelectionDraft, 'function');
  const parent = { project_id: 1, quantity: 2, addon_ids: [], diy_preferences: [], item_type: 'service' as const, chargeable: true, catalog_version_id: 10, option_choice_ids: [101], catalog_selection: { linked_snapshots: [{ linked_project_id: 3 }] } };
  const link = { ...parent, project_id: 3, quantity: 1, item_kind: 'catalog_linked_project', catalog_selection: undefined, catalog_version_id: undefined, option_choice_ids: [] };
  const restored = draftApi.hydrateSelectionDraft([parent, link]);
  assert.deepEqual(save(restored, 1).selectedProjectIds, [1, 1]);
  const independent = draftApi.hydrateSelectionDraft([parent, { ...link, item_kind: 'project', quantity: 2 }]);
  assert.deepEqual(save(independent, 1).selectedProjectIds, [1, 1, 3, 3]);
});

test('catalog-only links are expanded by server, not submitted as independent service lines', () => {
  const projects = [{ id: 1, category: 'bath', option_groups: [{ choices: [{ id: 101, linked_project_id: 3 }] }] }, { id: 3, category: 'small' }] as any;
  const linked = { ...save(draftApi.emptySelectionDraft(), 1, [3]), projectCatalogSelections: { 1: { projectId: 1, catalogVersionId: 10, optionChoiceIds: [101] } } };
  assert.deepEqual(buildSelectionItems({ ...linked, projects }).map(item => item.project_id), [1]);
  const independent = { ...linked, independentProjectIds: [1, 3, 3], selectedProjectIds: [1, 3, 3] };
  assert.equal(buildSelectionItems({ ...independent, projects }).find(item => item.project_id === 3)?.quantity, 2);
});

test('removing a linked line also unchecks its parent choice so server cannot resurrect it', () => {
  const projects = [{ id: 1, option_groups: [{ choices: [{ id: 101, linked_project_id: 3 }] }] }] as any;
  const draft = { ...save(draftApi.emptySelectionDraft(), 1, [3]), projectCatalogSelections: { 1: { projectId: 1, catalogVersionId: 10, optionChoiceIds: [101] } } };
  const removed = draftApi.removeSelectionEntry(draft, { kind: 'project', projectId: 3 }, projects);
  assert.deepEqual(removed.projectCatalogSelections?.[1].optionChoiceIds, []);
});

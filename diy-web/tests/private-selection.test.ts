import assert from 'node:assert/strict';
import test from 'node:test';
import { readPrivateSelection, writePrivateSelection, clearPrivateSelection, privateSubmitIntent, restorePrivateSelectionDraft } from '../src/privateSelection.ts';
import { removeSelectionEntry } from '../src/selectionSummary.ts';

function storage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); },
  };
}
const record = { storeId: 1, customerId: null, sessionId: 'private-one', accessToken: 'private-owner-token', items: [] };

test('private selection restores only the same store and customer context', () => {
  const local = storage();
  writePrivateSelection(local, record);
  assert.deepEqual(readPrivateSelection(local, 1, null), record);
  assert.equal(readPrivateSelection(local, 2, null), null);
  assert.equal(readPrivateSelection(local, 1, 42), null);
});

test('separate public-code browsers never share private carts', () => {
  const first = storage(), second = storage();
  writePrivateSelection(first, record);
  assert.equal(readPrivateSelection(second, 1, null), null);
  writePrivateSelection(second, { ...record, sessionId: 'private-two', accessToken: 'another-owner' });
  assert.equal(readPrivateSelection(first, 1, null)?.sessionId, 'private-one');
});

test('failed submission keeps its session and key across reload', () => {
  const local = storage();
  writePrivateSelection(local, { ...record, submitIntent: privateSubmitIntent(undefined, 'configured-items', () => 'first-key') });
  const restored = readPrivateSelection(local, 1, null)!;
  assert.equal(restored.sessionId, record.sessionId);
  assert.equal(restored.accessToken, record.accessToken);
  assert.deepEqual(privateSubmitIntent(restored.submitIntent, 'configured-items', () => 'wrong-key'), { signature: 'configured-items', key: 'first-key' });
  assert.equal(privateSubmitIntent(restored.submitIntent, 'edited-items', () => 'new-key').key, 'new-key');
});

test('logout drops private access without removing another store draft', () => {
  const local = storage();
  writePrivateSelection(local, { ...record, customerId: 42 });
  writePrivateSelection(local, { ...record, storeId: 2 });
  clearPrivateSelection(local, 1);
  assert.equal(readPrivateSelection(local, 1, 42), null);
  assert.equal(readPrivateSelection(local, 2, null)?.sessionId, record.sessionId);
});

test('legacy raw items recover linked references from the same server selection without replacing local choices', () => {
  const items = [{ project_id: 1, quantity: 2, item_type: 'service', addon_ids: [], diy_preferences: ['gentle'], catalog_version_id: 2, option_choice_ids: [3, 5] }];
  const server = [{ ...items[0], quantity: 1, catalog_selection: { linked_snapshots: [{ linked_project_id: 2 }] } }];
  const restored = restorePrivateSelectionDraft({ ...record, items }, server, []);
  assert.deepEqual(restored.selectedProjectIds, [1, 1, 2]);
  assert.deepEqual(restored.independentProjectIds, [1, 1]);
  assert.deepEqual(restored.projectLinkedIds, { 1: [2] });
  assert.deepEqual(restored.projectPreferences[1], ['gentle']);
});

test('unsynced legacy choices recover only from the same catalog version', () => {
  const items = [{ project_id: 1, quantity: 1, item_type: 'service', addon_ids: [], diy_preferences: [], catalog_version_id: 2, option_choice_ids: [5] }];
  const catalog = [{ id: 1, category: 'care', catalog_version_id: 2, option_groups: [{ choices: [{ id: 5, status: 'active', linked_project_id: 2 }] }] }];
  assert.deepEqual(restorePrivateSelectionDraft({ ...record, items }, [], catalog).projectLinkedIds, { 1: [2] });
  assert.deepEqual(restorePrivateSelectionDraft({ ...record, items }, [], [{ ...catalog[0], catalog_version_id: 3 }]).projectLinkedIds, { 1: [] });
});

test('legacy local selections keep their body parts instead of becoming independent generic projects', () => {
  const items = [{ project_id: 9, quantity: 2, item_type: 'service', addon_ids: [], diy_preferences: ['肩颈'] }];
  const restored = restorePrivateSelectionDraft({ ...record, items }, [], [{ id: 9, category: 'local-strength' }]);
  assert.deepEqual(restored.localParts, ['肩颈', '肩颈']);
  assert.deepEqual(restored.selectedProjectIds, []);
});

test('legacy independent child quantities never inherit a server-derived origin', () => {
  const base = { project_id: 1, quantity: 1, item_type: 'service', addon_ids: [], diy_preferences: [], catalog_version_id: 2, option_choice_ids: [5] };
  const child = { project_id: 2, quantity: 2, item_type: 'service', addon_ids: [], diy_preferences: [] };
  const server = [{ ...base, catalog_selection: { linked_snapshots: [{ linked_project_id: 2 }] } },
    { ...child, quantity: 1, item_kind: 'catalog_linked_project' }];
  const restored = restorePrivateSelectionDraft({ ...record, items: [base, child] }, server, []);
  assert.deepEqual(restored.independentProjectIds, [1, 2, 2]);
  assert.deepEqual(restored.selectedProjectIds, [1, 2, 2]);
  const removed = removeSelectionEntry(restored, { kind: 'project', projectId: 1 }, []);
  assert.deepEqual(removed.independentProjectIds, [2, 2]);
  assert.deepEqual(removed.selectedProjectIds, [2, 2]);
  const serverOnly = restorePrivateSelectionDraft({ ...record, items: undefined }, server, []);
  assert.deepEqual(serverOnly.independentProjectIds, [1]);
  assert.deepEqual(serverOnly.selectedProjectIds, [1, 2]);
});
